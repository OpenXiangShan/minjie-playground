"""Fixed-interval sampling using only existing BBVs and SimPoint labels."""

import gzip
import hashlib
import math
import random
from collections import defaultdict
from pathlib import Path


DEFAULT_OPTIONS = {
    "sampling_method": "simpoint",
    "num_samples": None,
    "seed": 42,
    "seedkm": 100000,
    "seedproj": 200000,
}


def add_sampling_arguments(parser):
    # None distinguishes an omitted option from an explicit change on resume.
    parser.add_argument("--sampling-method", choices=("simpoint", "random", "bbv-stratified"),
                        help="Selection method (default: simpoint; inherited on checkpoint resume)")
    parser.add_argument("--num-samples", type=int,
                        help="Exact sample budget, required for random and bbv-stratified")
    parser.add_argument("--seed", type=int, help="Sampling seed (default: 42)")
    parser.add_argument("--seedkm", type=int, help="SimPoint initialization seed (default: 100000)")
    parser.add_argument("--seedproj", type=int, help="SimPoint projection seed (default: 200000)")


def sampling_options_from_args(args):
    return {key: getattr(args, key) for key in DEFAULT_OPTIONS
            if getattr(args, key) is not None}


def resolve_sampling_options(options=None):
    result = {**DEFAULT_OPTIONS, **(options or {})}
    method = result["sampling_method"]
    budget = result["num_samples"]
    if method not in ("simpoint", "random", "bbv-stratified"):
        raise ValueError(f"unknown sampling method: {method}")
    if method == "simpoint":
        if budget is not None:
            raise ValueError("--num-samples applies only to random and bbv-stratified")
    elif budget is None or budget < 1:
        raise ValueError("--num-samples must be positive for random and bbv-stratified")
    for key in ("seed", "seedkm", "seedproj"):
        if not 0 <= result[key] <= 2147483647:
            raise ValueError(f"--{key} must be between 0 and 2147483647")
    return result


def inspect_bbv(path):
    """Count vectors without building a dense matrix; never renumber valid rows.

    Hash the decompressed input so gzip timestamps do not affect identity.
    Reject non-vector/empty rows rather than silently shifting checkpoint IDs.
    """
    digest = hashlib.sha256()
    count = 0
    with gzip.open(path, "rb") as handle:
        for count, raw in enumerate(handle, 1):
            digest.update(raw)
            line = raw.strip()
            if not line.startswith(b"T:"):
                raise ValueError(f"invalid or empty BBV at line {count}: {path}")
            positive = False
            for entry in line[1:].split():
                fields = entry.split(b":")
                if len(fields) != 3 or fields[0] or not all(v.isdigit() for v in fields[1:]):
                    raise ValueError(f"invalid BBV entry at line {count}: {path}")
                block, instructions = map(int, fields[1:])
                if block < 1:
                    raise ValueError(f"invalid basic block ID at line {count}: {path}")
                positive |= instructions > 0
            if not positive:
                raise ValueError(f"zero-mass BBV at line {count}: {path}")
    if not count:
        raise ValueError(f"empty BBV file: {path}")
    return count, digest.hexdigest()


def read_labels(path, num_intervals):
    """SimPoint -saveLabels emits '<cluster_id> <distance>' in vector order."""
    groups = defaultdict(list)
    with Path(path).open() as handle:
        for point, line in enumerate(handle):
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"invalid label row {point + 1}: {path}")
            label, distance = int(parts[0]), float(parts[1])
            if label < 0 or not math.isfinite(distance) or distance < 0:
                raise ValueError(f"invalid label/distance at row {point + 1}: {path}")
            groups[label].append(point)
    if sum(map(len, groups.values())) != num_intervals:
        raise ValueError("SimPoint label count does not match BBV interval count")
    return dict(sorted(groups.items()))


def allocate_samples(sizes, budget):
    """One per nonempty stratum, then proportional largest-remainder allocation.

    Cap saturated strata and redistribute their excess before rounding.
    Integer arithmetic and label tie-breaking make allocation reproducible.
    """
    if not sizes or any(size < 1 for size in sizes.values()):
        raise ValueError("strata must be nonempty")
    if not len(sizes) <= budget <= sum(sizes.values()):
        raise ValueError("sample budget must be between the number of strata and intervals; "
                         "reduce --max-k or increase --num-samples")
    allocation = dict.fromkeys(sizes, 1)
    remaining = budget - len(sizes)
    active = {label for label in sizes if sizes[label] > 1}
    while remaining:
        mass = sum(sizes[label] for label in active)
        saturated = [label for label in active
                     if remaining * sizes[label] >= (sizes[label] - allocation[label]) * mass]
        if saturated:
            for label in sorted(saturated):
                remaining -= sizes[label] - allocation[label]
                allocation[label] = sizes[label]
                active.remove(label)
            continue
        remainders = {}
        for label in sorted(active):
            extra, remainder = divmod(remaining * sizes[label], mass)
            allocation[label] += extra
            remainders[label] = remainder
        leftover = budget - sum(allocation.values())
        for label in sorted(active, key=lambda label: (-remainders[label], label))[:leftover]:
            allocation[label] += 1
        break
    return allocation


def select_samples(groups, budget, seed):
    sizes = {label: len(points) for label, points in groups.items()}
    allocation = allocate_samples(sizes, budget)
    total = sum(sizes.values())
    rng = random.Random(seed)
    samples = []
    strata = []
    for label in sorted(groups):
        size, selected = sizes[label], allocation[label]
        weight = size / (total * selected)
        strata.append({"cluster_id": label, "num_intervals": size,
                       "num_samples": selected, "weight": size / total})
        for point in rng.sample(groups[label], selected):
            samples.append({"interval_id": point, "cluster_id": label, "weight": weight})
    samples.sort(key=lambda item: item["interval_id"])
    for sample_id, sample in enumerate(samples):
        sample["sample_id"] = sample_id
    return samples, strata


def write_samples(output_dir, samples):
    if (not samples or len({s["interval_id"] for s in samples}) != len(samples)
            or any(not math.isfinite(s["weight"]) or s["weight"] <= 0 for s in samples)
            or not math.isclose(math.fsum(s["weight"] for s in samples), 1.0, abs_tol=1e-12)):
        raise ValueError("samples must be unique with positive weights summing to one")
    root = Path(output_dir)
    with (root / "simpoints0").open("w") as points, (root / "weights0").open("w") as weights:
        for sample in samples:
            points.write(f"{sample['interval_id']} {sample['sample_id']}\n")
            weights.write(f"{sample['weight']:.17g} {sample['sample_id']}\n")
