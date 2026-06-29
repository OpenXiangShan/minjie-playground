#!/usr/bin/env python3
"""Rank ML synthesis trials by a conservative PPA/runtime score."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_metric_files(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.is_dir():
            candidates = sorted(path.rglob("metrics.json"))
        else:
            candidates = [path]
        for candidate in candidates:
            try:
                rows.append(json.loads(candidate.read_text(errors="replace")))
            except (OSError, json.JSONDecodeError):
                continue
    return rows


def score(row: dict[str, Any]) -> float:
    if row.get("status") == "fail":
        return 1e9
    timing = row.get("timing", {})
    util = row.get("utilization", {})
    route = row.get("route", {})
    runtime = float(row.get("runtime_sec") or 0.0)
    value = runtime

    if route.get("route_complete") is False:
        value += 1e8
    wns = timing.get("wns")
    tns = timing.get("tns")
    if isinstance(wns, (int, float)) and wns < 0:
        value += abs(float(wns)) * 1e6
    if isinstance(tns, (int, float)) and tns < 0:
        value += abs(float(tns)) * 1e3

    value += float(util.get("clb_luts", 0.0)) * 0.1
    value += float(util.get("clb_registers", 0.0)) * 0.05
    value += float(util.get("block_ram_tile", 0.0)) * 2.0
    value += float(util.get("uram", 0.0)) * 2.0
    value += float(util.get("dsps", 0.0)) * 2.0
    return value


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "rank",
        "score",
        "trial_id",
        "status",
        "strategy_name",
        "runtime_sec",
        "wns",
        "tns",
        "route_complete",
        "clb_luts",
        "clb_registers",
        "block_ram_tile",
        "uram",
        "dsps",
        "failed_stages",
        "trial_dir",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for idx, row in enumerate(rows, start=1):
            timing = row.get("timing", {})
            util = row.get("utilization", {})
            route = row.get("route", {})
            writer.writerow(
                {
                    "rank": idx,
                    "score": row["_score"],
                    "trial_id": row.get("trial_id"),
                    "status": row.get("status"),
                    "strategy_name": row.get("strategy_name"),
                    "runtime_sec": row.get("runtime_sec"),
                    "wns": timing.get("wns"),
                    "tns": timing.get("tns"),
                    "route_complete": route.get("route_complete"),
                    "clb_luts": util.get("clb_luts"),
                    "clb_registers": util.get("clb_registers"),
                    "block_ram_tile": util.get("block_ram_tile"),
                    "uram": util.get("uram"),
                    "dsps": util.get("dsps"),
                    "failed_stages": ",".join(row.get("failed_stages", [])),
                    "trial_dir": row.get("trial_dir"),
                }
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank Vivado ML synthesis trials.")
    parser.add_argument("inputs", nargs="+", help="metrics.json files or directories")
    parser.add_argument(
        "--csv-out", default="build/ml_synth/summary.csv", help="CSV rank output"
    )
    args = parser.parse_args()

    rows = load_metric_files([REPO_ROOT / item for item in args.inputs])
    for row in rows:
        row["_score"] = score(row)
    rows.sort(key=lambda item: (item["_score"], item.get("runtime_sec") or 1e99))

    write_csv(REPO_ROOT / args.csv_out, rows)
    print(f"ranked {len(rows)} trials -> {REPO_ROOT / args.csv_out}")
    for idx, row in enumerate(rows[:10], start=1):
        print(
            f"{idx:02d} score={row['_score']:.3f} status={row.get('status')} "
            f"trial={row.get('trial_id')} strategy={row.get('strategy_name')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
