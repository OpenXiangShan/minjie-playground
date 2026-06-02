import argparse
import os
import subprocess

from generate_checkpoint import load_nemu_paths
from generate_checkpoint import profiling_dir
from generate_checkpoint import profiling_log_dir
from generate_checkpoint import profiling_stage_name


CHECKPOINT_FORMAT = "zstd"


def build_profiling_command(*,
                            nemu_bin: str,
                            workload_bin: str,
                            archive_root: str,
                            workload: str,
                            interval: int,
                            cpu_bind: str,
                            mem_bind: str) -> list[str]:
    return [
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


def run_profiling_step(*,
                       archive_root: str,
                       workload: str,
                       workload_bin: str,
                       interval: int,
                       cpu_bind: str = "0",
                       mem_bind: str = "0") -> int:
    nemu_paths = load_nemu_paths()
    os.makedirs(profiling_dir(archive_root, workload), exist_ok=True)
    log_dir = profiling_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    out_log = os.path.join(log_dir, "profiling.out.log")
    err_log = os.path.join(log_dir, "profiling.err.log")

    command = build_profiling_command(
        nemu_bin=nemu_paths.nemu,
        workload_bin=workload_bin,
        archive_root=archive_root,
        workload=workload,
        interval=interval,
        cpu_bind=cpu_bind,
        mem_bind=mem_bind,
    )

    with open(out_log, "w", encoding="utf-8") as out, open(
            err_log, "w", encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        proc.wait()
    return proc.returncode


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the profiling step")
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--workload-bin", required=True)
    parser.add_argument("--interval", type=int, default=20_000_000)
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
        cpu_bind=args.cpu_bind,
        mem_bind=args.mem_bind,
    )


if __name__ == "__main__":
    raise SystemExit(main())
