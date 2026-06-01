import argparse
import concurrent.futures
import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

AUTO_RESUME = "auto"
COMPLETE_STATE = "complete"
AUTO_RESUME_BACKUP_SUFFIX = "auto-resume-full"
KNOWN_WORKLOAD_SUFFIXES = (
    ".fw_payload.bin",
    ".bin",
)


@dataclass(frozen=True)
class NemuPaths:
    home: str
    nemu: str
    simpoint: str


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)


def resolve_output_base_dir() -> str:
    override = os.environ.get("CHECKPOINT_OUTPUT_BASE")
    if override:
        return os.path.realpath(override)
    return os.path.realpath("archive")


def build_archive_root(archive_id: str) -> str:
    return os.path.realpath(os.path.join(resolve_output_base_dir(), archive_id))


def require_env_path(env_var: str) -> str:
    value = os.environ.get(env_var)
    if not value:
        raise EnvironmentError(f"{env_var} is not set")
    if not os.path.isdir(value):
        raise EnvironmentError(f"{env_var} does not point to a directory: {value}")
    return value


def load_nemu_paths() -> NemuPaths:
    nemu_home = require_env_path("NEMU_HOME")
    paths = NemuPaths(
        home=nemu_home,
        nemu=os.path.join(nemu_home, "build", "riscv64-nemu-interpreter"),
        simpoint=os.path.join(
            nemu_home,
            "resource",
            "simpoint",
            "simpoint_repo",
            "bin",
            "simpoint",
        ),
    )
    missing = [
        path for path in [paths.nemu, paths.simpoint] if not os.path.isfile(path)
    ]
    if missing:
        raise FileNotFoundError(
            "required runtime tool missing: " + ", ".join(missing))
    return paths


def _normalize_ids(ids):
    return tuple(int(item) for item in ids)


def format_stage_name(base: str, *ids) -> str:
    normalized = _normalize_ids(ids)
    if not normalized or all(item == 0 for item in normalized):
        return base
    return f"{base}-{'-'.join(str(item) for item in normalized)}"


def profiling_stage_name(profiling_id=0) -> str:
    return format_stage_name("profiling", profiling_id)


def cluster_stage_name(profiling_id=0, cluster_id=0) -> str:
    return format_stage_name("cluster", profiling_id, cluster_id)


def checkpoint_stage_name(profiling_id=0, cluster_id=0, checkpoint_id=0) -> str:
    return format_stage_name("checkpoint", profiling_id, cluster_id,
                             checkpoint_id)


def archive_layout(archive_root: str) -> dict[str, str]:
    return {
        "logs": os.path.join(archive_root, "logs"),
        "metadata": os.path.join(archive_root, "metadata"),
        "json": os.path.join(archive_root, "json"),
    }


def profiling_dir(archive_root: str, workload: str, profiling_id=0) -> str:
    return os.path.join(archive_root, profiling_stage_name(profiling_id),
                        workload)


def cluster_dir(archive_root: str,
                workload: str,
                profiling_id=0,
                cluster_id=0) -> str:
    return os.path.join(archive_root,
                        cluster_stage_name(profiling_id, cluster_id), workload)


def checkpoint_dir(archive_root: str,
                   workload: str,
                   profiling_id=0,
                   cluster_id=0,
                   checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        workload,
    )


def profiling_log_dir(archive_root: str, workload: str, profiling_id=0) -> str:
    return os.path.join(archive_root, "logs", profiling_stage_name(profiling_id),
                        workload)


def cluster_log_dir(archive_root: str,
                    workload: str,
                    profiling_id=0,
                    cluster_id=0) -> str:
    return os.path.join(
        archive_root,
        "logs",
        cluster_stage_name(profiling_id, cluster_id),
        workload,
    )


def checkpoint_log_dir(archive_root: str,
                       workload: str,
                       profiling_id=0,
                       cluster_id=0,
                       checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        "logs",
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        workload,
    )


def workload_json_path(archive_root: str, workload: str) -> str:
    return os.path.join(archive_root, "json", f"{workload}.json")


def checkpoint_list_path(archive_root: str,
                         profiling_id=0,
                         cluster_id=0,
                         checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        "checkpoint.lst",
    )


def json_output_dir(base_path: str, checkpoint_name: str) -> str:
    if checkpoint_name == "checkpoint":
        return os.path.join(base_path, "json")
    return os.path.join(base_path, "json", checkpoint_name)


def count_checkpoints(archive_root: str, workload: str) -> int:
    from step_checkpoint import count_checkpoints as _count_checkpoints

    return _count_checkpoints(archive_root, workload)


def validate_outputs(archive_root: str, workload: str) -> None:
    from step_checkpoint import validate_outputs as _validate_outputs

    _validate_outputs(archive_root, workload)


def generate_checkpoint_metadata(archive_root, workloads, times, ids):
    from step_metadata import generate_checkpoint_metadata as _generate_metadata

    _generate_metadata(archive_root, workloads, times, ids)


def build_archive_layout(archive_root: str) -> dict[str, str]:
    return archive_layout(archive_root)


def ensure_directories(paths) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)


def derive_archive_label(input_path: str | None) -> str:
    if not input_path:
        return "bins"
    label = os.path.basename(os.path.normpath(input_path))
    return safe_name(label) or "bins"


def generate_archive_id(mode: str,
                        workload: str | None = None,
                        input_path: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if mode == "file":
        return f"{timestamp}_{safe_name(workload or 'workload')}"
    if mode == "directory":
        return f"{timestamp}_{derive_archive_label(input_path)}"
    raise ValueError(f"unsupported archive mode: {mode}")


def write_request_metadata(metadata_dir: str,
                           request: dict,
                           filename: str = "request.yaml") -> str:
    os.makedirs(metadata_dir, exist_ok=True)
    output_path = os.path.join(metadata_dir, filename)
    lines = []
    for key, value in request.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = value
        lines.append(f"{key}: {rendered}")
    lines.append(f"timestamp: {datetime.now().isoformat(timespec='seconds')}")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(str(line) for line in lines) + "\n")
    return output_path


def remove_path(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def clear_aggregate_metadata(archive_root: str) -> None:
    for path in [
            os.path.join(archive_root, "json", "checkpoints_cov0.3.json"),
            os.path.join(archive_root, "json", "checkpoints_all.json"),
            checkpoint_list_path(archive_root),
            os.path.join(archive_root, "checkpoint-0-0-0", "checkpoint.lst"),
            os.path.join(archive_root, "checkpoint-0-0-0", "cluster-0-0.json"),
    ]:
        remove_path(path)


def validate_resume_artifacts(archive_root: str, workload: str,
                              resume_after: str | None) -> None:
    required = []
    if resume_after == "profiling":
        required = [os.path.join(profiling_dir(archive_root, workload), "simpoint_bbv.gz")]
    elif resume_after == "cluster":
        required = [
            os.path.join(cluster_dir(archive_root, workload), "simpoints0"),
            os.path.join(cluster_dir(archive_root, workload), "weights0"),
        ]

    for path in required:
        if not os.path.exists(path):
            raise FileNotFoundError(f"required resume artifact missing: {path}")


def parse_simpoint_points(simpoints_path: str) -> list[str]:
    points = []
    with open(simpoints_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if parts:
                points.append(parts[0])
    return points


def read_cluster_rows(cluster_output_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    simpoint_rows = {}
    weight_rows = {}

    with open(os.path.join(cluster_output_dir, "simpoints0"),
              "r",
              encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if len(parts) >= 2:
                point, cluster_id = parts[0], parts[1]
                simpoint_rows[point] = cluster_id

    with open(os.path.join(cluster_output_dir, "weights0"),
              "r",
              encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if len(parts) >= 2:
                weight, cluster_id = parts[0], parts[1]
                weight_rows[cluster_id] = weight

    return simpoint_rows, weight_rows


def checkpoint_point_has_artifact(point_dir: str) -> bool:
    if not os.path.isdir(point_dir):
        return False
    return any(name.endswith((".gz", ".zstd")) for name in os.listdir(point_dir))


def detect_auto_resume_state(archive_root: str, workload: str) -> dict[str, object]:
    profiling_path = os.path.join(profiling_dir(archive_root, workload),
                                  "simpoint_bbv.gz")
    workload_cluster_dir = cluster_dir(archive_root, workload)
    simpoints_path = os.path.join(workload_cluster_dir, "simpoints0")
    weights_path = os.path.join(workload_cluster_dir, "weights0")
    simpoints_read_path = (f"{simpoints_path}.{AUTO_RESUME_BACKUP_SUFFIX}"
                           if os.path.exists(
                               f"{simpoints_path}.{AUTO_RESUME_BACKUP_SUFFIX}")
                           else simpoints_path)
    workload_checkpoint_dir = checkpoint_dir(archive_root, workload)

    if not os.path.exists(profiling_path):
        return {
            "state": "fresh",
            "resume_after": None,
            "skip": False,
            "expected_points": [],
            "present_points": [],
            "missing_points": [],
        }

    if not (os.path.exists(simpoints_path) and os.path.exists(weights_path)):
        return {
            "state": "after_profiling",
            "resume_after": "profiling",
            "skip": False,
            "expected_points": [],
            "present_points": [],
            "missing_points": [],
        }

    expected_points = parse_simpoint_points(simpoints_read_path)
    present_points = [
        point for point in expected_points
        if checkpoint_point_has_artifact(os.path.join(workload_checkpoint_dir, point))
    ]
    missing_points = [
        point for point in expected_points if point not in set(present_points)
    ]

    if expected_points and not missing_points:
        return {
            "state": COMPLETE_STATE,
            "resume_after": None,
            "skip": True,
            "expected_points": expected_points,
            "present_points": present_points,
            "missing_points": [],
        }

    return {
        "state": "after_cluster",
        "resume_after": "cluster",
        "skip": False,
        "expected_points": expected_points,
        "present_points": present_points,
        "missing_points": missing_points,
    }


def backup_file_once(path: str, suffix: str) -> None:
    if not os.path.exists(path):
        return
    backup_path = f"{path}.{suffix}"
    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)


def restore_auto_resume_artifacts(archive_root: str, workload: str) -> None:
    workload_cluster_dir = cluster_dir(archive_root, workload)
    for name in ["simpoints0", "weights0"]:
        path = os.path.join(workload_cluster_dir, name)
        backup_path = f"{path}.{AUTO_RESUME_BACKUP_SUFFIX}"
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, path)


def prepare_auto_resume_artifacts(archive_root: str, workload: str,
                                  state: dict[str, object]) -> str | None:
    resume_after = state["resume_after"]
    if resume_after != "cluster":
        return resume_after

    missing_points = list(state.get("missing_points", []))
    present_points = list(state.get("present_points", []))
    if not missing_points or not present_points:
        return resume_after

    workload_cluster_dir = cluster_dir(archive_root, workload)
    simpoints_path = os.path.join(workload_cluster_dir, "simpoints0")
    weights_path = os.path.join(workload_cluster_dir, "weights0")
    restore_auto_resume_artifacts(archive_root, workload)
    backup_file_once(simpoints_path, AUTO_RESUME_BACKUP_SUFFIX)
    backup_file_once(weights_path, AUTO_RESUME_BACKUP_SUFFIX)

    simpoint_rows, weight_rows = read_cluster_rows(workload_cluster_dir)
    with open(simpoints_path, "w", encoding="utf-8") as simpoints, open(
            weights_path, "w", encoding="utf-8") as weights:
        for new_cluster_id, point in enumerate(missing_points):
            old_cluster_id = simpoint_rows[point]
            print(f"{point} {new_cluster_id}", file=simpoints)
            print(f"{weight_rows[old_cluster_id]} {new_cluster_id}", file=weights)

    return resume_after


def inspect_input_kind(input_path: str) -> str:
    if os.path.isfile(input_path):
        return "file"
    if os.path.isdir(input_path):
        return "directory"
    raise FileNotFoundError(f"input path does not exist: {input_path}")


def validate_input_args(args) -> None:
    if not os.path.exists(args.input_path):
        raise FileNotFoundError(f"input path does not exist: {args.input_path}")
    if not os.access(args.input_path, os.R_OK):
        raise PermissionError(f"input path is not readable: {args.input_path}")

    input_kind = inspect_input_kind(args.input_path)
    if input_kind == "directory" and args.name is not None:
        raise ValueError("--name can only be used with a single file input")

    if args.resume_after is not None and args.archive_id is None:
        raise ValueError("--archive-id is required when using --resume-after")

    if args.max_workers < 1:
        raise ValueError("--max-workers must be at least 1")
    if args.interval <= 0:
        raise ValueError("--interval must be a positive integer")
    if args.max_k is not None and args.max_k <= 0:
        raise ValueError("--max-k must be a positive integer")


def ensure_resume_logs(archive_root: str, workload: str,
                       resume_after: str | None) -> None:
    if resume_after is None:
        return
    log_dir = profiling_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    for name in ["profiling.out.log", "profiling.err.log"]:
        path = os.path.join(log_dir, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("")


def reset_stage_outputs(archive_root: str, workload: str,
                        resume_after: str | None,
                        preserve_checkpoint_workload: bool = False) -> None:
    if resume_after is None:
        stages_to_remove = ("profiling", "cluster", "checkpoint")
    elif resume_after == "profiling":
        stages_to_remove = ("cluster", "checkpoint")
    elif resume_after == "cluster":
        stages_to_remove = ("checkpoint",)
    else:
        raise ValueError(f"unsupported resume stage: {resume_after}")

    stage_paths = {
        "profiling": [
            profiling_dir(archive_root, workload),
            profiling_log_dir(archive_root, workload),
        ],
        "cluster": [
            cluster_dir(archive_root, workload),
            cluster_log_dir(archive_root, workload),
        ],
        "checkpoint": [
            checkpoint_log_dir(archive_root, workload),
            workload_json_path(archive_root, workload),
            os.path.join(archive_root, "checkpoint-0-0-0", "cluster-0-0.json"),
            os.path.join(archive_root, "checkpoint-0-0-0", "checkpoint.lst"),
        ],
    }
    if not preserve_checkpoint_workload:
        stage_paths["checkpoint"].insert(0, checkpoint_dir(archive_root, workload))

    for stage in stages_to_remove:
        for path in stage_paths[stage]:
            remove_path(path)


def build_single_run_args(input_path: str, workload_name: str | None,
                          archive_id: str | None, interval: int,
                          max_workers: int,
                          max_k: int | None,
                          resume_after: str | None) -> argparse.Namespace:
    return argparse.Namespace(
        input_path=input_path,
        name=workload_name,
        archive_id=archive_id,
        interval=interval,
        max_workers=max_workers,
        max_k=max_k,
        resume_after=resume_after,
    )


def get_worker_bindings(index: int, numa_nodes: int = 2) -> tuple[str, str]:
    node = str(index % max(1, numa_nodes))
    return node, node


def strip_known_bin_suffix(file_name: str) -> str:
    for suffix in KNOWN_WORKLOAD_SUFFIXES:
        if file_name.endswith(suffix) and len(file_name) > len(suffix):
            return file_name[:-len(suffix)]
    return Path(file_name).stem


def longest_common_suffix(names: list[str]) -> str:
    if not names:
        return ""
    reversed_names = [name[::-1] for name in names]
    return os.path.commonprefix(reversed_names)[::-1]


def derive_common_bin_suffix(names: list[str]) -> str:
    for suffix in KNOWN_WORKLOAD_SUFFIXES:
        if all(name.endswith(suffix) for name in names):
            return suffix

    common_suffix = longest_common_suffix(names)
    if not common_suffix:
        return ""

    for marker in [".", "_", "-"]:
        index = common_suffix.find(marker)
        if index > 0:
            return common_suffix[index:]
    return common_suffix


def derive_directory_entries(input_dir: str) -> tuple[list[dict[str, str]], str]:
    files = sorted(entry for entry in Path(input_dir).iterdir() if entry.is_file())
    if not files:
        raise ValueError(f"input directory does not contain any files: {input_dir}")

    basenames = [entry.name for entry in files]
    common_suffix = derive_common_bin_suffix(basenames)
    entries = []
    seen_names = set()

    for file_path in files:
        workload_name = file_path.name
        if common_suffix and len(workload_name) > len(common_suffix):
            workload_name = workload_name[:-len(common_suffix)]
        workload_name = workload_name.rstrip(".-_") or strip_known_bin_suffix(
            file_path.name)
        if not workload_name:
            raise ValueError(
                f"unable to derive workload name from file: {file_path}")
        if workload_name in seen_names:
            raise ValueError(
                f"duplicate workload name derived from input directory: {workload_name}")

        entries.append({"bin": str(file_path), "name": workload_name})
        seen_names.add(workload_name)

    return entries, common_suffix


def load_input_entries(input_path: str,
                       name_override: str | None = None
                       ) -> tuple[str, list[dict[str, str]], str | None]:
    input_kind = inspect_input_kind(input_path)
    if input_kind == "file":
        workload_name = name_override or strip_known_bin_suffix(
            os.path.basename(os.path.normpath(input_path)))
        return "file", [{"bin": input_path, "name": workload_name}], None
    entries, common_suffix = derive_directory_entries(input_path)
    return "directory", entries, common_suffix


def run_workload(*,
                 bin_path: str,
                 workload_name: str,
                 archive_root: str,
                 interval: int,
                 max_k: int | None,
                 resume_after: str | None,
                 cpu_bind: str = "0",
                 mem_bind: str = "0",
                 metadata_dir: str | None = None,
                 generate_metadata: bool = True) -> dict[str, str | int]:
    from step_checkpoint import run_checkpoint_step
    from step_profiling import run_profiling_step
    from step_cluster import run_cluster_step

    layout = build_archive_layout(archive_root)
    ensure_directories(layout.values())
    load_nemu_paths()

    effective_resume_after = resume_after
    preserve_checkpoint_workload = False
    if resume_after == AUTO_RESUME:
        state = detect_auto_resume_state(archive_root, workload_name)
        if state["skip"]:
            workload_checkpoint_dir = checkpoint_dir(archive_root, workload_name)
            return {
                "name": workload_name,
                "archive_id": os.path.basename(archive_root),
                "archive_root": archive_root,
                "checkpoint_count": count_checkpoints(archive_root, workload_name),
                "checkpoint_dir": workload_checkpoint_dir,
                "skipped": 1,
            }
        effective_resume_after = prepare_auto_resume_artifacts(
            archive_root, workload_name, state)
        preserve_checkpoint_workload = bool(state.get("present_points"))

    request = {
        "bin": os.path.realpath(bin_path),
        "name": workload_name,
        "archive_id": os.path.basename(archive_root),
        "interval": interval,
        "max_k": max_k,
        "resume_after": resume_after,
    }
    request_dir = metadata_dir or layout["metadata"]
    metadata_path = write_request_metadata(request_dir,
                                           request,
                                           filename=f"{workload_name}.yaml")
    print(
        f"[Workload] name={workload_name} archive={os.path.basename(archive_root)} input={os.path.realpath(bin_path)}",
        flush=True,
    )

    reset_stage_outputs(
        archive_root,
        workload_name,
        effective_resume_after,
        preserve_checkpoint_workload=preserve_checkpoint_workload,
    )
    validate_resume_artifacts(archive_root, workload_name, effective_resume_after)
    ensure_resume_logs(archive_root, workload_name, effective_resume_after)

    try:
        if effective_resume_after is None:
            print(
                f"[Profiling] start workload={workload_name} interval={interval} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            profiling_rc = run_profiling_step(
                archive_root=archive_root,
                workload=workload_name,
                workload_bin=bin_path,
                interval=interval,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
            )
            if profiling_rc != 0:
                print(f"Warning: profiling exited with code {profiling_rc} for {workload_name}")
            else:
                print(
                    f"[Profiling] done workload={workload_name} log={profiling_log_dir(archive_root, workload_name)}",
                    flush=True,
                )
            print(
                f"[Clustering] start workload={workload_name} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            run_cluster_step(
                archive_root=archive_root,
                workload=workload_name,
                max_k=max_k,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
            )
            print(
                f"[Clustering] done workload={workload_name} log={cluster_log_dir(archive_root, workload_name)}",
                flush=True,
            )
        elif effective_resume_after == "profiling":
            print(
                f"[Clustering] resume workload={workload_name} from=profiling cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            run_cluster_step(
                archive_root=archive_root,
                workload=workload_name,
                max_k=max_k,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
            )
            print(
                f"[Clustering] done workload={workload_name} log={cluster_log_dir(archive_root, workload_name)}",
                flush=True,
            )
        elif effective_resume_after != "cluster":
            raise ValueError(f"unsupported resume stage: {effective_resume_after}")

        if effective_resume_after == "cluster":
            print(
                f"[Checkpoint] resume workload={workload_name} from=cluster cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
        else:
            print(
                f"[Checkpoint] start workload={workload_name} interval={interval} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
        checkpoint_rc = run_checkpoint_step(
            archive_root=archive_root,
            workload=workload_name,
            workload_bin=bin_path,
            interval=interval,
            cpu_bind=cpu_bind,
            mem_bind=mem_bind,
        )
        if checkpoint_rc != 0:
            print(
                f"Warning: checkpoint step exited with code {checkpoint_rc} for {workload_name}")
        else:
            print(
                f"[Checkpoint] done workload={workload_name} log={checkpoint_log_dir(archive_root, workload_name)}",
                flush=True,
            )
    finally:
        if resume_after == AUTO_RESUME:
            restore_auto_resume_artifacts(archive_root, workload_name)

    validate_outputs(archive_root, workload_name)
    if generate_metadata:
        print(f"[Metadata] start workload={workload_name}", flush=True)
        clear_aggregate_metadata(archive_root)
        generate_checkpoint_metadata(
            archive_root=archive_root,
            workloads=[workload_name],
            times=[1, 1, 1],
            ids=[0, 0, 0],
        )
        print(f"[Metadata] done workload={workload_name}", flush=True)

    workload_checkpoint_dir = checkpoint_dir(archive_root, workload_name)
    print(
        f"[Workload] done name={workload_name} checkpoints={count_checkpoints(archive_root, workload_name)} dir={workload_checkpoint_dir}",
        flush=True,
    )
    return {
        "name": workload_name,
        "archive_id": os.path.basename(archive_root),
        "archive_root": archive_root,
        "checkpoint_count": count_checkpoints(archive_root, workload_name),
        "checkpoint_dir": workload_checkpoint_dir,
        "metadata": metadata_path,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=
        "Run profiling, cluster, checkpoint, and metadata from one bin or a directory of bins",
    )
    parser.add_argument("--input-path",
                        required=True,
                        help="Path to a GCPT-bootable bin file or a directory of bin files")
    parser.add_argument("--name",
                        help="Optional workload name override used only with a single input file")
    parser.add_argument("--archive-id", help="Existing or new archive id")
    parser.add_argument("--interval",
                        type=int,
                        default=20_000_000,
                        help="Checkpoint interval")
    parser.add_argument("--max-k",
                        type=int,
                        help="Optional SimPoint maxK override; effective value is max(workload default, user value)")
    parser.add_argument("--max-workers",
                        type=int,
                        default=3,
                        help="Maximum parallel workloads used in directory mode")
    parser.add_argument("--resume-after",
                        choices=["profiling", "cluster", AUTO_RESUME],
                        help="Resume from a later stage")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    validate_input_args(args)

    input_mode, entries, common_suffix = load_input_entries(args.input_path,
                                                            args.name)
    for entry in entries:
        validate_input_args(
            build_single_run_args(input_path=entry["bin"],
                                  workload_name=entry["name"],
                                  archive_id=args.archive_id,
                                  interval=args.interval,
                                  max_workers=args.max_workers,
                                  max_k=args.max_k,
                                  resume_after=args.resume_after))

    if input_mode == "file":
        archive_id = args.archive_id or generate_archive_id("file",
                                                            entries[0]["name"])
        archive_root = build_archive_root(archive_id)
        ensure_directories(build_archive_layout(archive_root).values())
        clear_aggregate_metadata(archive_root)
        write_request_metadata(
            os.path.join(archive_root, "metadata"),
            {
                "mode": "file",
                "input_path": os.path.realpath(args.input_path),
                "name": entries[0]["name"],
                "archive_id": archive_id,
                "interval": args.interval,
                "max_k": args.max_k,
                "resume_after": args.resume_after,
            },
        )
        print(f"Archive: {archive_id}", flush=True)
        print(f"Archive root: {archive_root}", flush=True)
        run_workload(
            bin_path=entries[0]["bin"],
            workload_name=entries[0]["name"],
            archive_root=archive_root,
            interval=args.interval,
            max_k=args.max_k,
            resume_after=args.resume_after,
        )
        return 0

    archive_id = args.archive_id or generate_archive_id("directory",
                                                        input_path=args.input_path)
    archive_root = build_archive_root(archive_id)
    layout = build_archive_layout(archive_root)
    ensure_directories(layout.values())
    clear_aggregate_metadata(archive_root)
    write_request_metadata(
        layout["metadata"],
        {
            "mode": "directory",
            "input_path": os.path.realpath(args.input_path),
            "archive_id": archive_id,
            "interval": args.interval,
            "max_k": args.max_k,
            "resume_after": args.resume_after,
            "max_workers": args.max_workers,
            "common_suffix": common_suffix or "",
            "workloads": [entry["name"] for entry in entries],
        },
        filename="batch_request.yaml",
    )

    print(f"Batch size: {len(entries)}", flush=True)
    print(f"Archive: {archive_id}", flush=True)
    print(f"Archive root: {archive_root}", flush=True)
    print(f"Max workers: {args.max_workers}", flush=True)
    if args.max_k is not None:
        print(f"Max k override: {args.max_k}", flush=True)
    if common_suffix:
        print(f"Derived common suffix: {common_suffix}", flush=True)

    results = []
    failures = []
    requests_dir = os.path.join(layout["metadata"], "requests")
    os.makedirs(requests_dir, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.max_workers) as executor:
        future_to_entry = {}
        for index, entry in enumerate(entries):
            cpu_bind, mem_bind = get_worker_bindings(index)
            print(
                f"=== [{index + 1}/{len(entries)}] Checkpointing {entry['name']} from {entry['bin']} (cpu={cpu_bind}, mem={mem_bind}) ===",
                flush=True,
            )
            future = executor.submit(run_workload,
                                     bin_path=entry["bin"],
                                     workload_name=entry["name"],
                                     archive_root=archive_root,
                                     interval=args.interval,
                                     max_k=args.max_k,
                                     resume_after=args.resume_after,
                                     cpu_bind=cpu_bind,
                                     mem_bind=mem_bind,
                                     metadata_dir=requests_dir,
                                     generate_metadata=False)
            future_to_entry[future] = entry

        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"name": entry["name"], "error": str(exc)})

    if failures:
        print("Batch failures:", flush=True)
        for failure in failures:
            print(f"- {failure['name']}: {failure['error']}", flush=True)
        return 1

    print("[Metadata] start workload=batch", flush=True)
    generate_checkpoint_metadata(
        archive_root=archive_root,
        workloads=[entry["name"] for entry in entries],
        times=[1, 1, 1],
        ids=[0, 0, 0],
    )
    print("[Metadata] done workload=batch", flush=True)

    print("Batch summary:", flush=True)
    for result in results:
        suffix = ", skipped=complete" if result.get("skipped") else ""
        print(
            f"- {result['name']}: archive={result['archive_id']}, checkpoints={result['checkpoint_count']}, dir={result['checkpoint_dir']}{suffix}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
