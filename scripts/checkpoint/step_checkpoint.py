import argparse
import os
import subprocess

from generate_checkpoint import checkpoint_dir
from generate_checkpoint import checkpoint_log_dir
from generate_checkpoint import checkpoint_stage_name
from generate_checkpoint import cluster_dir
from generate_checkpoint import load_nemu_paths
from generate_checkpoint import profiling_dir
from step_metadata import cluster_weight


COMPRESSED_CHECKPOINT_SUFFIXES = (".gz", ".zstd")
CHECKPOINT_FORMAT = "zstd"


def build_checkpoint_command(*,
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


def run_checkpoint_step(*,
                        archive_root: str,
                        workload: str,
                        workload_bin: str,
                        interval: int,
                        cpu_bind: str = "0",
                        mem_bind: str = "0") -> int:
    nemu_paths = load_nemu_paths()
    os.makedirs(checkpoint_dir(archive_root, workload), exist_ok=True)
    log_dir = checkpoint_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    command = build_checkpoint_command(
        nemu_bin=nemu_paths.nemu,
        workload_bin=workload_bin,
        archive_root=archive_root,
        workload=workload,
        interval=interval,
        cpu_bind=cpu_bind,
        mem_bind=mem_bind,
    )

    with open(os.path.join(log_dir, "checkpoint.out.log"), "w",
              encoding="utf-8") as out, open(
                  os.path.join(log_dir, "checkpoint.err.log"), "w",
                  encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err)
        proc.wait()
    return proc.returncode


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the checkpoint step")
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--workload-bin", required=True)
    parser.add_argument("--interval", type=int, default=20_000_000)
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
        cpu_bind=args.cpu_bind,
        mem_bind=args.mem_bind,
    )


if __name__ == "__main__":
    raise SystemExit(main())
