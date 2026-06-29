#!/usr/bin/env python3
"""Parse Vivado trial logs/reports into a stable ML synthesis metrics record."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(read_text(path))
    except json.JSONDecodeError:
        return {}


def parse_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in read_text(path).splitlines():
        if "=" not in line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def as_number(raw: str) -> float | None:
    raw = raw.strip().replace(",", "")
    if not raw or raw in {"-", "_"}:
        return None
    if raw.startswith("<"):
        raw = raw[1:]
    try:
        return float(raw)
    except ValueError:
        return None


def parse_time_file(path: Path) -> dict[str, float | int]:
    result: dict[str, float | int] = {}
    for key, value in parse_kv_file(path).items():
        if key == "returncode":
            try:
                result[key] = int(value)
            except ValueError:
                pass
        else:
            num = as_number(value)
            if num is not None:
                result[key] = num
    return result


def parse_logs(log_dir: Path) -> dict[str, Any]:
    stages: dict[str, Any] = {}
    if not log_dir.is_dir():
        return stages
    for time_path in sorted(log_dir.glob("*.time")):
        stage = time_path.stem
        stages.setdefault(stage, {}).update(parse_time_file(time_path))
    for log_path in sorted(log_dir.glob("*.log")):
        stage = log_path.stem
        text = read_text(log_path)
        stage_data = stages.setdefault(stage, {})
        stage_data["log"] = str(log_path)
        if re.search(r"\bERROR:|\bfailed\b|Command failed", text, re.IGNORECASE):
            stage_data["has_error"] = True
            errors = [
                line.strip()
                for line in text.splitlines()
                if re.search(r"\bERROR:|\bfailed\b|Command failed", line, re.IGNORECASE)
            ]
            stage_data["error_examples"] = errors[-8:]
        else:
            stage_data["has_error"] = False
    return stages


def parse_timing_summary(path: Path) -> dict[str, float]:
    text = read_text(path)
    result: dict[str, float] = {}
    patterns = {
        "wns": r"\bWNS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
        "tns": r"\bTNS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
        "whs": r"\bWHS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
        "ths": r"\bTHS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
        "wpws": r"\bWPWS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
        "tpws": r"\bTPWS(?:\(ns\))?\s*\|?\s*(-?\d+(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            result[key] = float(match.group(1))
    # Common table row format:
    # | Design Timing Summary | WNS(ns) | TNS(ns) | ...
    table_match = re.search(
        r"\|\s*Design Timing Summary\s*\|.*?\n(?:\+[-+\s]+\+\n)?\|\s*(-?\d+(?:\.\d+)?)\s*\|\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if table_match:
        result.setdefault("wns", float(table_match.group(1)))
        result.setdefault("tns", float(table_match.group(2)))
    return result


def parse_utilization(path: Path) -> dict[str, float]:
    text = read_text(path)
    result: dict[str, float] = {}
    label_map = {
        "clb_luts": r"CLB LUTs\*?",
        "lut_as_logic": r"LUT as Logic",
        "lut_as_memory": r"LUT as Memory",
        "clb_registers": r"CLB Registers",
        "block_ram_tile": r"Block RAM Tile",
        "uram": r"\bURAM\b",
        "dsps": r"\bDSPs\b",
    }
    for key, label in label_map.items():
        pattern = rf"\|\s*{label}\s*\|\s*([<,\d.]+)\s*\|"
        match = re.search(pattern, text)
        if match:
            value = as_number(match.group(1))
            if value is not None:
                result[key] = value
    return result


def parse_route_status(path: Path) -> dict[str, Any]:
    text = read_text(path)
    result: dict[str, Any] = {}
    lower = text.lower()
    if "design is fully routed" in lower:
        result["route_complete"] = True
    elif "unrouted" in lower or "not fully routed" in lower:
        result["route_complete"] = False
    if text:
        result["has_route_report"] = True
    return result


def find_first(root: Path, names: list[str]) -> Path | None:
    for name in names:
        direct = root / name
        if direct.is_file():
            return direct
    for name in names:
        matches = sorted(root.rglob(name))
        if matches:
            return matches[0]
    return None


def parse_trial(trial_dir: Path) -> dict[str, Any]:
    config = read_json(trial_dir / "config.json")
    logs = parse_logs(trial_dir / "logs")
    reports_dir = trial_dir / "reports"
    timing_path = find_first(reports_dir, ["timing_summary.rpt"])
    util_path = find_first(reports_dir, ["utilization.rpt"])
    route_path = find_first(reports_dir, ["route_status.rpt"])

    timing = parse_timing_summary(timing_path) if timing_path else {}
    utilization = parse_utilization(util_path) if util_path else {}
    route = parse_route_status(route_path) if route_path else {}
    run_status = parse_kv_file(reports_dir / "run_status.txt")

    failed_stages = [
        stage
        for stage, data in logs.items()
        if data.get("has_error") or data.get("returncode", 0) not in (0, None)
    ]
    bitstream_path = None
    suffix = config.get("suffix", "")
    cpu = config.get("cpu", "")
    if suffix and cpu:
        flow_dir = REPO_ROOT / config.get("flow_dir", "env-scripts/fpga_diff")
        prj_name = f"fpga_{cpu}-{suffix}"
        bit_matches = sorted((flow_dir / prj_name).glob("**/*.bit"))
        if bit_matches:
            bitstream_path = str(bit_matches[0])

    status = "pass"
    if failed_stages:
        status = "fail"
    elif not bitstream_path and logs.get("bitstream"):
        status = "incomplete"

    runtime_sec = sum(
        float(data.get("elapsed_sec", 0.0))
        for data in logs.values()
        if isinstance(data, dict)
    )

    return {
        "schema_version": 1,
        "trial_dir": str(trial_dir),
        "trial_id": config.get("trial_id"),
        "target_name": config.get("target_name"),
        "strategy_name": config.get("strategy_name"),
        "suffix": config.get("suffix"),
        "cpu": config.get("cpu"),
        "jobs": config.get("jobs"),
        "strategy": config.get("strategy", {}),
        "status": status,
        "failed_stages": failed_stages,
        "runtime_sec": runtime_sec if runtime_sec > 0 else None,
        "stages": logs,
        "run_status": run_status,
        "timing": timing,
        "utilization": utilization,
        "route": route,
        "bitstream_path": bitstream_path,
        "known_current_issue": config.get("known_current_issue", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Parse Vivado reports/logs for an ML synthesis trial."
    )
    parser.add_argument("--trial-dir", required=True, help="Trial output directory")
    parser.add_argument("--json-out", help="Write parsed metrics JSON")
    args = parser.parse_args()

    metrics = parse_trial((REPO_ROOT / args.trial_dir).resolve())
    text = json.dumps(metrics, indent=2, sort_keys=True)
    print(text)
    if args.json_out:
        out = REPO_ROOT / args.json_out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
