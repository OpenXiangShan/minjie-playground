import argparse
import json
import os
import re
from itertools import product
from pathlib import Path

from generate_checkpoint import checkpoint_list_path
from generate_checkpoint import checkpoint_stage_name
from generate_checkpoint import cluster_stage_name
from generate_checkpoint import json_output_dir
from generate_checkpoint import profiling_stage_name


INSTRUCTION_REGEX = re.compile(r".*total guest instructions = (.*)\x1b.*")


def profiling_instrs(profiling_log, spec_app, using_step_layout=False):
    new_path = os.path.join(profiling_log, spec_app, "profiling.out.log")
    old_path = os.path.join(profiling_log, f"{spec_app}-out.log")

    if using_step_layout:
        path = new_path
        if not os.path.exists(new_path):
            raise FileNotFoundError(new_path)
    elif os.path.exists(old_path):
        path = old_path
    elif os.path.exists(new_path):
        path = new_path
    else:
        raise FileNotFoundError(f"missing profiling log: {old_path} or {new_path}")

    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if "total guest instructions" not in line:
                continue
            match = INSTRUCTION_REGEX.findall(line)
            if not match:
                raise ValueError(f"failed to parse instructions from {path}")
            return match[0].replace(",", "")
    raise ValueError(f"failed to find instructions in {path}")


def cluster_weight(cluster_path, spec_app):
    points = {}
    weights = {}

    weights_path = Path(cluster_path) / spec_app / "weights0"
    simpoints_path = Path(cluster_path) / spec_app / "simpoints0"

    with weights_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            weight, cluster_id = line.split()
            weights[cluster_id] = weight

    with simpoints_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            point, cluster_id = line.split()
            if float(weights[cluster_id]) > 1e-4:
                points[point] = weights[cluster_id]

    return points


def build_workload_metadata(profiling_log, cluster_path, spec_app):
    return {
        "insts": profiling_instrs(profiling_log, spec_app),
        "points": cluster_weight(cluster_path, spec_app),
    }


def write_json_file(target_path, payload):
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=4) + "\n", encoding="utf-8")


def build_aggregated_json(json_result, coverage_limit=None):
    result = {}
    for workload, info in json_result.items():
        result[workload] = {
            "insts": info["insts"],
            "points": {},
        }
        cumulative_weight = 0.0
        sorted_points = sorted(info["points"].items(),
                               key=lambda item: float(item[1]),
                               reverse=True)
        for point, weight in sorted_points:
            result[workload]["points"][point] = weight
            cumulative_weight += float(weight)
            if coverage_limit is not None and cumulative_weight >= coverage_limit:
                break
    return result


def per_checkpoint_generate_json(profiling_log, cluster_path, app_list, target_dir):
    result = {}
    target_root = Path(target_dir)
    target_root.mkdir(parents=True, exist_ok=True)

    for spec in app_list:
        workload_metadata = build_workload_metadata(profiling_log, cluster_path,
                                                    spec)
        result[spec] = workload_metadata
        write_json_file(target_root / f"{spec}.json", {spec: workload_metadata})

    write_json_file(target_root / "checkpoints_all.json",
                    build_aggregated_json(result))
    write_json_file(target_root / "checkpoints_cov0.3.json",
                    build_aggregated_json(result, coverage_limit=0.3))
    return result


def per_checkpoint_generate_worklist(cpt_path, target_path, json_result):
    checkpoint_root = Path(cpt_path)
    target = Path(target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not checkpoint_root.exists():
        target.write_text("", encoding="utf-8")
        return

    with target.open("w", encoding="utf-8") as handle:
        for workload_dir in sorted(entry for entry in checkpoint_root.iterdir()
                                   if entry.is_dir()):
            for checkpoint_dir in sorted(entry
                                         for entry in workload_dir.iterdir()
                                         if entry.is_dir()):
                workload = workload_dir.name
                point = checkpoint_dir.name
                if point not in json_result[workload]["points"]:
                    continue
                rel_path = checkpoint_dir.relative_to(checkpoint_root).as_posix()
                name = f"{workload}_{point}"
                print(f"{name} {rel_path} 0 0 20 20", file=handle)


def generate_result_list(base_path, times, ids):
    result_list = []
    for profiling_id, cluster_id, checkpoint_id in product(
            range(ids[0], times[0]),
            range(ids[1], times[1]),
            range(ids[2], times[2]),
    ):
        cluster = cluster_stage_name(profiling_id, cluster_id)
        profiling = profiling_stage_name(profiling_id)
        checkpoint = checkpoint_stage_name(profiling_id, cluster_id,
                                           checkpoint_id)
        result_list.append({
            "cluster_path":
            os.path.join(base_path, cluster),
            "profiling_log":
            os.path.join(base_path, "logs", profiling),
            "checkpoint_path":
            os.path.join(base_path, checkpoint),
            "json_dir":
            json_output_dir(base_path, checkpoint),
            "list_path":
            checkpoint_list_path(base_path, profiling_id, cluster_id,
                                 checkpoint_id),
        })
    return result_list


def generate_metadata(base_path, workloads, times, ids):
    result_list = generate_result_list(base_path, times, ids)
    for result in result_list:
        json_result = per_checkpoint_generate_json(
            result["profiling_log"],
            result["cluster_path"],
            workloads,
            result["json_dir"],
        )
        per_checkpoint_generate_worklist(
            result["checkpoint_path"],
            result["list_path"],
            json_result,
        )


def generate_checkpoint_metadata(archive_root, workloads, times, ids):
    generate_metadata(
        base_path=archive_root,
        workloads=sorted(set(workloads)),
        times=times,
        ids=ids,
    )


def parse_csv_ints(value):
    return [int(item) for item in value.split(",")]


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Generate checkpoint metadata and worklists",
    )
    parser.add_argument("--base-path", required=True, help="Checkpoint archive root")
    parser.add_argument("--workloads",
                        required=True,
                        help="Comma-separated workload names")
    parser.add_argument("--times",
                        default="1,1,1",
                        help="Comma-separated profiling,cluster,checkpoint counts")
    parser.add_argument("--ids",
                        default="0,0,0",
                        help="Comma-separated profiling,cluster,checkpoint start ids")
    return parser


def main():
    args = build_arg_parser().parse_args()
    workloads = [item for item in args.workloads.split(",") if item]
    generate_metadata(
        base_path=args.base_path,
        workloads=workloads,
        times=parse_csv_ints(args.times),
        ids=parse_csv_ints(args.ids),
    )


if __name__ == "__main__":
    main()
