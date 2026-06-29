#!/usr/bin/env python3
"""Generate reproducible Vivado DSE trial specs for ML synthesis research."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(errors="replace"))


def stable_token(text: str) -> str:
    safe = []
    for char in text.lower():
        if char.isalnum():
            safe.append(char)
        elif char in {"-", "_", "."}:
            safe.append("-")
    token = "".join(safe).strip("-")
    while "--" in token:
        token = token.replace("--", "-")
    return token or "trial"


def iter_trial_specs(
    targets: dict,
    search_space: dict,
    *,
    run_id: str,
    limit: int | None,
) -> list[dict]:
    specs: list[dict] = []
    idx = 0
    for target in targets.get("targets", []):
        for strategy in search_space.get("trials", []):
            if limit is not None and len(specs) >= limit:
                return specs
            idx += 1
            strategy_name = strategy.get("name", f"trial-{idx}")
            target_name = target.get("name", "target")
            suffix = f"mlsynth-{run_id}-{idx:04d}-{stable_token(strategy_name)[:32]}"
            output_root = Path(target.get("output_root", "build/ml_synth")).as_posix()
            specs.append(
                {
                    "schema_version": 1,
                    "trial_id": f"{run_id}-{idx:04d}",
                    "target_name": target_name,
                    "strategy_name": strategy_name,
                    "suffix": suffix,
                    "repo_root": str(REPO_ROOT),
                    "flow_dir": target["flow_dir"],
                    "core_dir": target.get("core_dir_default", ""),
                    "core_dir_env": target.get("core_dir_env", ""),
                    "design": target.get("design", ""),
                    "cpu": target["cpu"],
                    "jobs": int(target.get("jobs", 1)),
                    "output_dir": str(Path(output_root) / run_id / suffix),
                    "make_project_target": target.get("make_project_target", "all"),
                    "make_synth_target": target.get("make_synth_target", "synth"),
                    "make_bitstream_target": target.get("make_bitstream_target", "bitstream"),
                    "strategy": strategy,
                    "known_current_issue": target.get("known_current_issue", ""),
                }
            )
    return specs


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate ML synthesis Vivado trial specs."
    )
    parser.add_argument(
        "--targets",
        default="ml_synth/configs/targets.nutshell.json",
        help="Target config JSON",
    )
    parser.add_argument(
        "--search-space",
        default="ml_synth/configs/search_space.vivado.json",
        help="Vivado search-space JSON",
    )
    parser.add_argument(
        "--run-id",
        default=dt.datetime.now().strftime("%Y%m%d-%H%M%S"),
        help="Stable run ID used in trial IDs and SUFFIX values",
    )
    parser.add_argument("--limit", type=int, help="Limit number of generated trials")
    parser.add_argument(
        "--out",
        default="build/ml_synth/trials.jsonl",
        help="Output JSONL trial file",
    )
    args = parser.parse_args()

    targets = load_json(REPO_ROOT / args.targets)
    search_space = load_json(REPO_ROOT / args.search_space)
    specs = iter_trial_specs(
        targets,
        search_space,
        run_id=stable_token(args.run_id),
        limit=args.limit,
    )
    out_path = REPO_ROOT / args.out
    write_jsonl(out_path, specs)

    print(f"wrote {len(specs)} trial specs: {out_path}")
    for spec in specs:
        print(
            f"{spec['trial_id']}: {spec['target_name']} "
            f"{spec['strategy_name']} -> {spec['suffix']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
