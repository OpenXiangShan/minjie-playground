import argparse
import os
import subprocess

from generate_checkpoint import checkpoint_dir
from generate_checkpoint import checkpoint_log_dir
from generate_checkpoint import checkpoint_stage_name
from generate_checkpoint import cluster_dir
from generate_checkpoint import cluster_stage_name
from generate_checkpoint import load_nemu_paths
from generate_checkpoint import load_qemu_paths
from generate_checkpoint import profiling_dir
from generate_checkpoint import profiling_log_dir
from generate_checkpoint import QEMU_CPU
from generate_checkpoint import resolve_qemu_memory
from generate_checkpoint import validate_virtual_workload
from step_metadata import cluster_weight
from virtual_checkpoint import DEFAULT_START_MARKER
from virtual_checkpoint import DEFAULT_STOP_MARKER
from virtual_checkpoint import parse_virtual_profiling_logs
from virtual_checkpoint import validate_virtual_checkpoint_logs
from virtual_checkpoint import virtual_checkpoint_max_instr


COMPRESSED_CHECKPOINT_SUFFIXES = (".gz", ".zstd")
CHECKPOINT_FORMAT = "zstd"
PROCESS_TERMINATE_TIMEOUT_SECONDS = 10


def build_checkpoint_command(*,
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
                             virtual_checkpoint_limit: int | None = None) -> list[str]:
    command = [
        "numactl",
        f"--cpunodebind={cpu_bind}",
        f"--membind={mem_bind}",
        nemu_bin,
        workload_bin,
        "-D",
        archive_root,
        "-w",
        workload,
        "-C",
        checkpoint_stage_name(),
        "-b",
        "-S",
        os.path.join(archive_root, "cluster"),
        "--cpt-interval",
        str(interval),
        "--checkpoint-format",
        CHECKPOINT_FORMAT,
    ]
    if virtualized:
        if virtual_checkpoint_limit is None:
            raise ValueError("virtual_checkpoint_limit is required")
        command.extend([
            "--start-profiling-on-uart-marker",
            virtual_start_marker,
            "--stop-profiling-on-uart-marker",
            virtual_stop_marker,
            "-I",
            str(virtual_checkpoint_limit),
        ])
    return command


def build_qemu_checkpoint_command(*,
                                  qemu_bin: str,
                                  workload_bin: str,
                                  archive_root: str,
                                  workload: str,
                                  interval: int,
                                  copies: int,
                                  qemu_memory: str) -> list[str]:
    machine = (
        f"nemu,simpoint-path={os.path.join(archive_root, cluster_stage_name())},"
        f"workload={workload},"
        f"cpt-interval={interval},"
        f"output-base-dir={archive_root},"
        f"config-name={checkpoint_stage_name()},"
        "checkpoint-mode=SimpointCheckpoint")
    return [
        qemu_bin,
        "-bios",
        workload_bin,
        "-M",
        machine,
        "-nographic",
        "-m",
        qemu_memory,
        "-smp",
        str(copies),
        "-cpu",
        QEMU_CPU,
    ]


def checkpoint_point_has_artifact(point_dir: str) -> bool:
    if not os.path.isdir(point_dir):
        return False
    return any(name.endswith(COMPRESSED_CHECKPOINT_SUFFIXES)
               for name in os.listdir(point_dir))


def count_checkpoints(archive_root: str, workload: str) -> int:
    workload_checkpoint_dir = checkpoint_dir(archive_root, workload)
    return sum(
        1 for root, _, files in os.walk(workload_checkpoint_dir)
        for name in files if name.endswith(COMPRESSED_CHECKPOINT_SUFFIXES))


def validate_outputs(archive_root: str, workload: str) -> None:
    required = [
        os.path.join(profiling_dir(archive_root, workload), "simpoint_bbv.gz"),
        os.path.join(cluster_dir(archive_root, workload), "simpoints0"),
        os.path.join(cluster_dir(archive_root, workload), "weights0"),
    ]
    for path in required:
        if not os.path.exists(path):
            raise FileNotFoundError(f"expected output missing: {path}")

    workload_checkpoint_dir = checkpoint_dir(archive_root, workload)
    if not os.path.isdir(workload_checkpoint_dir):
        raise FileNotFoundError(
            f"expected checkpoint output directory missing: {workload_checkpoint_dir}")

    checkpoint_count = count_checkpoints(archive_root, workload)
    if checkpoint_count == 0:
        raise FileNotFoundError(
            f"no compressed checkpoint artifacts found under: {workload_checkpoint_dir}")

    expected_points = cluster_weight(os.path.join(archive_root, "cluster"),
                                     workload)
    missing_points = []
    for point in sorted(expected_points):
        point_dir = os.path.join(workload_checkpoint_dir, point)
        if not checkpoint_point_has_artifact(point_dir):
            missing_points.append(point)

    if missing_points:
        raise FileNotFoundError(
            "missing compressed checkpoint artifacts for expected simpoints: "
            + ", ".join(missing_points))


def terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=PROCESS_TERMINATE_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_checkpoint_step(*,
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
                        virtual_max_instr: int | None = None,
                        virtual_checkpoint_limit: int | None = None) -> int:
    os.makedirs(checkpoint_dir(archive_root, workload), exist_ok=True)
    log_dir = checkpoint_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    if virtualized:
        if copies != 1:
            raise ValueError("virtualized checkpoint generation requires copies=1")
        if qemu_memory is not None:
            raise ValueError("qemu_memory cannot be used for virtualized checkpoints")
        if not virtual_start_marker or not virtual_stop_marker:
            raise ValueError("virtualized checkpoint markers cannot be empty")
        if virtual_max_instr is not None and virtual_max_instr <= 0:
            raise ValueError("virtual_max_instr must be positive")
        validate_virtual_workload(workload_bin)
        if virtual_checkpoint_limit is None:
            profiling_log = profiling_log_dir(archive_root, workload)
            evidence = parse_virtual_profiling_logs(
                [
                    os.path.join(profiling_log, "profiling.out.log"),
                    os.path.join(profiling_log, "profiling.err.log"),
                ],
                virtual_start_marker,
                virtual_stop_marker,
            )
            virtual_checkpoint_limit = virtual_checkpoint_max_instr(
                evidence.marker_base,
                os.path.join(cluster_dir(archive_root, workload), "simpoints0"),
                interval,
                virtual_max_instr,
            )
    elif virtual_max_instr is not None:
        raise ValueError("virtual_max_instr requires virtualized checkpoints")

    if copies > 1:
        qemu_paths = load_qemu_paths()
        command = build_qemu_checkpoint_command(
            qemu_bin=qemu_paths.qemu,
            workload_bin=workload_bin,
            archive_root=archive_root,
            workload=workload,
            interval=interval,
            copies=copies,
            qemu_memory=resolve_qemu_memory(workload_bin, qemu_memory),
        )
    else:
        nemu_paths = load_nemu_paths()
        command = build_checkpoint_command(
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
            virtual_checkpoint_limit=virtual_checkpoint_limit,
        )

    with open(os.path.join(log_dir, "checkpoint.out.log"), "w",
              encoding="utf-8") as out, open(
                  os.path.join(log_dir, "checkpoint.err.log"), "w",
                  encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        try:
            proc.wait()
        except BaseException:
            terminate_process(proc)
            raise
    if virtualized and proc.returncode == 0:
        validate_virtual_checkpoint_logs(
            [
                os.path.join(log_dir, "checkpoint.out.log"),
                os.path.join(log_dir, "checkpoint.err.log"),
            ],
            virtual_start_marker,
        )
    return proc.returncode


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the checkpoint step")
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
    return run_checkpoint_step(
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
