import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

from generate_checkpoint import cluster_dir, cluster_log_dir, profiling_dir
from sampling import (add_sampling_arguments, inspect_bbv, read_labels,
                      resolve_sampling_options, sampling_options_from_args,
                      select_samples, write_samples)


def max_k_for_workload(workload: str, requested_max_k: int | None = None) -> int:
    if requested_max_k is not None:
        if requested_max_k < 1:
            raise ValueError("--max-k must be positive")
        return requested_max_k
    return 100 if workload == "xalancbmk" else 30


def build_cluster_command(*, simpoint_bin: str, archive_root: str,
                          workload: str, cpu_bind: str, mem_bind: str,
                          max_k: int | None, seedkm: int, seedproj: int,
                          output_dir: str | None = None) -> list[str]:
    output_dir = output_dir or cluster_dir(archive_root, workload)
    return [
        "numactl", f"--cpunodebind={cpu_bind}", f"--membind={mem_bind}",
        simpoint_bin,
        "-loadFVFile", os.path.join(profiling_dir(archive_root, workload), "simpoint_bbv.gz"),
        "-saveSimpoints", os.path.join(output_dir, "simpoints0"),
        "-saveSimpointWeights", os.path.join(output_dir, "weights0"),
        "-saveLabels", os.path.join(output_dir, "labels0"),
        "-inputVectorsGzipped", "-fixedLength", "on",
        "-maxK", str(max_k_for_workload(workload, max_k)),
        "-numInitSeeds", "2", "-iters", "1000",
        "-seedkm", str(seedkm), "-seedproj", str(seedproj),
    ]


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resume_sampling_options(archive_root, workload, options, max_k):
    """Inherit saved choices, rejecting explicit changes before resume mutates files."""
    path = Path(cluster_dir(archive_root, workload)) / "sampling.json"
    if not path.exists():
        if options or max_k is not None:
            raise ValueError("legacy cluster has no sampling.json; resume without sampling "
                             "options, or use --resume-after profiling to select new points")
        return {}
    saved = json.loads(path.read_text())
    for key, value in (options or {}).items():
        if saved["options"].get(key) != value:
            raise ValueError(f"cannot change {key} when reusing cluster outputs; "
                             "use --resume-after profiling or a new cluster-only experiment")
    if max_k is not None and max_k != saved["requested_max_k"]:
        raise ValueError("cannot change --max-k when reusing cluster outputs")
    return saved["options"]


def run_cluster_step(*, archive_root: str, workload: str,
                     max_k: int | None = None, cpu_bind: str = "0",
                     mem_bind: str = "0", sampling_options: dict | None = None,
                     output_dir: str | None = None) -> dict:
    options = resolve_sampling_options(sampling_options)
    method, budget = options["sampling_method"], options["num_samples"]
    bbv = Path(profiling_dir(archive_root, workload)) / "simpoint_bbv.gz"
    count, bbv_hash = inspect_bbv(bbv)
    if budget is not None and budget > count:
        raise ValueError(f"--num-samples {budget} exceeds {count} available intervals")
    effective_max_k = None
    simpoint_bin = None
    if method != "random":
        effective_max_k = min(max_k_for_workload(workload, max_k), count)
        if method == "bbv-stratified":
            # The budget bounds the number of nonempty strata. Explicit --max-k
            # may be smaller, allowing multiple samples per stratum.
            effective_max_k = min(effective_max_k, budget)
        if count > 1:
            nemu_home = os.environ.get("NEMU_HOME")
            if not nemu_home:
                raise EnvironmentError("NEMU_HOME is required for SimPoint clustering")
            simpoint_bin = str(Path(nemu_home) / "resource/simpoint/simpoint_repo/bin/simpoint")
            if not os.access(simpoint_bin, os.X_OK):
                raise FileNotFoundError(f"missing executable SimPoint: {simpoint_bin}")
    elif max_k is not None:
        raise ValueError("--max-k does not apply to random sampling")

    target = Path(output_dir or cluster_dir(archive_root, workload)).resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise FileExistsError(f"cluster output is not empty: {target}; choose a new output directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Publish the points, weights, labels and provenance together only on success.
    with tempfile.TemporaryDirectory(prefix=f".{target.name}-", dir=target.parent) as temporary:
        root = Path(temporary)
        command = None
        tool_info = None
        if simpoint_bin:
            command = build_cluster_command(
                simpoint_bin=simpoint_bin, archive_root=archive_root, workload=workload,
                cpu_bind=cpu_bind, mem_bind=mem_bind, max_k=effective_max_k,
                seedkm=options["seedkm"], seedproj=options["seedproj"], output_dir=temporary)
            with (root / "cluster.out.log").open("w") as out, (root / "cluster.err.log").open("w") as err:
                try:
                    subprocess.run(command, stdout=out, stderr=err, check=True)
                except (OSError, subprocess.CalledProcessError) as exc:
                    err.flush()
                    out.flush()
                    tail = (root / "cluster.err.log").read_text(errors="replace")[-4000:]
                    tail += (root / "cluster.out.log").read_text(errors="replace")[-4000:]
                    raise RuntimeError(f"SimPoint failed: {exc}\n{tail}") from exc
            if not (root / "labels0").exists():
                tail = (root / "cluster.out.log").read_text(errors="replace")[-4000:]
                raise RuntimeError(f"SimPoint produced no labels for {count} intervals\n{tail}")
            groups = read_labels(root / "labels0", count)
            tool_info = {"path": os.path.realpath(simpoint_bin), "sha256": file_sha256(simpoint_bin)}
        else:
            groups = {0: range(count)}
            if method != "random":
                # SimPoint 3.2 emits no outputs for a one-vector input.
                # Its sole interval is the entire population, with weight 1.
                (root / "labels0").write_text("0 0\n")
                (root / "simpoints0").write_text("0 0\n")
                (root / "weights0").write_text("1 0\n")

        if method == "simpoint":
            samples = []
            weights = {}
            for line in (root / "weights0").read_text().splitlines():
                weight, label = line.split()
                weights[int(label)] = float(weight)
            for line in (root / "simpoints0").read_text().splitlines():
                point, label = map(int, line.split())
                if point not in groups[label]:
                    raise ValueError("SimPoint representative does not belong to its cluster")
                samples.append({"interval_id": point, "sample_id": label,
                                "cluster_id": label, "weight": weights[label]})
            if len(samples) != len(groups):
                raise ValueError("SimPoint outputs do not cover every nonempty cluster")
            strata = [{"cluster_id": label, "num_intervals": len(points),
                       "num_samples": 1, "weight": weights[label]}
                      for label, points in groups.items()]
        else:
            if method == "bbv-stratified":
                (root / "simpoints0").rename(root / "centroid_simpoints0")
                (root / "weights0").rename(root / "centroid_weights0")
            samples, strata = select_samples(groups, budget, options["seed"])
            write_samples(root, samples)

        metadata = {
            "schema_version": 1,
            "options": options,
            "requested_max_k": max_k,
            "effective_max_k": effective_max_k,
            "num_intervals": count,
            "actual_num_samples": len(samples),
            "weighting": "equal-length instruction intervals; full BBV population",
            "bbv_path": str(bbv.resolve()),
            "bbv_sha256_decompressed": bbv_hash,
            "python_version": platform.python_version(),
            "sampler_sha256": file_sha256(Path(__file__).with_name("sampling.py")),
            "selector_sha256": file_sha256(__file__),
            "simpoint": tool_info,
            "command": command,
            "strata": strata,
            "samples": samples,
        }
        (root / "sampling.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if not simpoint_bin:
            (root / "cluster.out.log").write_text(f"Selected {len(samples)} of {count} intervals using seed {options['seed']}\n")
            (root / "cluster.err.log").touch()
        os.replace(root, target)
    if output_dir is None:
        log_dir = Path(cluster_log_dir(archive_root, workload))
        log_dir.mkdir(parents=True, exist_ok=True)
        for name in ("cluster.out.log", "cluster.err.log"):
            shutil.copy2(target / name, log_dir / name)
    print(f"[Sampling] method={method} intervals={count} samples={len(samples)} output={target}", flush=True)
    return metadata


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Select checkpoint intervals from an existing BBV")
    parser.add_argument("--archive-root", required=True)
    parser.add_argument("--workload", required=True)
    parser.add_argument("--max-k", type=int, help="Exact SimPoint search upper bound")
    parser.add_argument("--cpu-bind", default="0")
    parser.add_argument("--mem-bind", default="0")
    parser.add_argument("--output-dir", help="New experiment directory; existing nonempty directories are rejected")
    add_sampling_arguments(parser)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    run_cluster_step(archive_root=args.archive_root, workload=args.workload,
                     max_k=args.max_k, cpu_bind=args.cpu_bind, mem_bind=args.mem_bind,
                     sampling_options=sampling_options_from_args(args), output_dir=args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
