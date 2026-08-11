import argparse
import os
import subprocess

from generate_checkpoint import load_qemu_paths
from generate_checkpoint import load_nemu_paths
from generate_checkpoint import profiling_dir
from generate_checkpoint import profiling_log_dir
from generate_checkpoint import profiling_stage_name
from generate_checkpoint import QEMU_CPU
from generate_checkpoint import resolve_qemu_memory
from generate_checkpoint import validate_virtual_workload
from virtual_checkpoint import DEFAULT_START_MARKER
from virtual_checkpoint import DEFAULT_STOP_MARKER
from virtual_checkpoint import parse_virtual_profiling_logs
from virtual_checkpoint import validate_virtual_bbv


CHECKPOINT_FORMAT = "zstd"


def build_profiling_command(*,
                            nemu_bin: str,
                            workload_bin: str,
                            archive_root: str,
                            workload: str,
                            interval: int,
                            cpu_bind: str,
                            mem_bind: str,
                            virtualized: bool = False,
                            virtual_start_marker: str = DEFAULT_START_MARKER,
                            virtual_stop_marker: str = DEFAULT_STOP_MARKER,
                            virtual_max_instr: int | None = None) -> list[str]:
    command = [
        "numactl",
        f"--cpunodebind={cpu_bind}",
        f"--membind={mem_bind}",
        nemu_bin,
        workload_bin,
        "-D",
        archive_root,
        "-C",
        profiling_stage_name(),
        "-w",
        workload,
        "-b",
        "--simpoint-profile",
        "--cpt-interval",
        str(interval),
        "--checkpoint-format",
        CHECKPOINT_FORMAT,
    ]
    if virtualized:
        command.extend([
            "--start-profiling-on-uart-marker",
            virtual_start_marker,
            "--stop-profiling-on-uart-marker",
            virtual_stop_marker,
        ])
        if virtual_max_instr is not None:
            command.extend(["-I", str(virtual_max_instr)])
    return command


def build_qemu_profiling_command(*,
                                 qemu_bin: str,
                                 profiling_plugin: str,
                                 workload_bin: str,
                                 archive_root: str,
                                 workload: str,
                                 interval: int,
                                 copies: int,
                                 qemu_memory: str,
                                 cpu_bind: str,
                                 mem_bind: str) -> list[str]:
    return [
        "numactl",
        f"--cpunodebind={cpu_bind}",
        f"--membind={mem_bind}",
        qemu_bin,
        "-bios",
        workload_bin,
        "-M",
        "nemu",
        "-nographic",
        "-m",
        qemu_memory,
        "-smp",
        str(copies),
        "-cpu",
        QEMU_CPU,
        "-plugin",
        "{},workload={},intervals={},target={}".format(
            profiling_plugin,
            workload,
            interval,
            os.path.join(archive_root, profiling_stage_name(), workload),
        ),
    ]


def run_profiling_step(*,
                       archive_root: str,
                       workload: str,
                       workload_bin: str,
                       interval: int,
                       copies: int = 1,
                       qemu_memory: str | None = None,
                       cpu_bind: str = "0",
                       mem_bind: str = "0",
                       virtualized: bool = False,
                       virtual_start_marker: str = DEFAULT_START_MARKER,
                       virtual_stop_marker: str = DEFAULT_STOP_MARKER,
                       virtual_max_instr: int | None = None) -> int:
    os.makedirs(profiling_dir(archive_root, workload), exist_ok=True)
    log_dir = profiling_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    out_log = os.path.join(log_dir, "profiling.out.log")
    err_log = os.path.join(log_dir, "profiling.err.log")

    if virtualized:
        if copies != 1:
            raise ValueError("virtualized profiling requires copies=1")
        if qemu_memory is not None:
            raise ValueError("qemu_memory cannot be used for virtualized profiling")
        if not virtual_start_marker or not virtual_stop_marker:
            raise ValueError("virtualized profiling markers cannot be empty")
        if virtual_max_instr is not None and virtual_max_instr <= 0:
            raise ValueError("virtual_max_instr must be positive")
        validate_virtual_workload(workload_bin)
    elif virtual_max_instr is not None:
        raise ValueError("virtual_max_instr requires virtualized profiling")

    if copies > 1:
        qemu_paths = load_qemu_paths()
        command = build_qemu_profiling_command(
            qemu_bin=qemu_paths.qemu,
            profiling_plugin=qemu_paths.profiling_plugin,
            workload_bin=workload_bin,
            archive_root=archive_root,
            workload=workload,
            interval=interval,
            copies=copies,
            qemu_memory=resolve_qemu_memory(workload_bin, qemu_memory),
            cpu_bind=cpu_bind,
            mem_bind=mem_bind,
        )
    else:
        nemu_paths = load_nemu_paths()
        command = build_profiling_command(
            nemu_bin=nemu_paths.nemu,
            workload_bin=workload_bin,
            archive_root=archive_root,
            workload=workload,
            interval=interval,
            cpu_bind=cpu_bind,
            mem_bind=mem_bind,
            virtualized=virtualized,
            virtual_start_marker=virtual_start_marker,
            virtual_stop_marker=virtual_stop_marker,
            virtual_max_instr=virtual_max_instr,
        )

    with open(out_log, "w", encoding="utf-8") as out, open(
            err_log, "w", encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        proc.wait()
    if virtualized and proc.returncode == 0:
        parse_virtual_profiling_logs(
            [out_log, err_log], virtual_start_marker, virtual_stop_marker)
        validate_virtual_bbv(
            os.path.join(profiling_dir(archive_root, workload), "simpoint_bbv.gz"))
    return proc.returncode


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the profiling step")
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--workload-bin", required=True)
    parser.add_argument("--interval", type=int, default=20_000_000)
    parser.add_argument("--copies", type=int, default=1)
    parser.add_argument("--qemu-memory")
    parser.add_argument("--virtualized", action="store_true")
    parser.add_argument("--virtual-start-marker", default=DEFAULT_START_MARKER)
    parser.add_argument("--virtual-stop-marker", default=DEFAULT_STOP_MARKER)
    parser.add_argument("--virtual-max-instr", type=int)
    parser.add_argument("--cpu-bind", default="0")
    parser.add_argument("--mem-bind", default="0")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    return run_profiling_step(
        archive_root=args.archive_root,
        workload=args.workload,
        workload_bin=args.workload_bin,
        interval=args.interval,
        copies=args.copies,
        qemu_memory=args.qemu_memory,
        cpu_bind=args.cpu_bind,
        mem_bind=args.mem_bind,
        virtualized=args.virtualized,
        virtual_start_marker=args.virtual_start_marker,
        virtual_stop_marker=args.virtual_stop_marker,
        virtual_max_instr=args.virtual_max_instr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
