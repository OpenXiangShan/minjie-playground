#!/usr/bin/env python3
"""Summarize XiangShan simulator logs without modifying run artifacts."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


OUT_NAMES = ("simulator_out.txt", "simulation_out.txt", "stdout.log")
ERR_NAMES = ("simulator_err.txt", "simulation_err.txt", "stderr.log")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
INSTR_RE = re.compile(r"instrCnt\s*=\s*([0-9][0-9,]*)", re.IGNORECASE)
SIGNALS = {
    "stuck": re.compile(
        r"No instruction of core\s+\d+\s+commits for\s+"
        r"[0-9][0-9,]*\s+cycles,?\s+maybe get stuck",
        re.IGNORECASE,
    ),
    "liveness": re.compile(
        r"\b(?:deadlock|livelock|watchdog(?:\s+timeout)?)\b|"
        r"\b(?:resource|entry|request|queue|buffer)\s+leak\b",
        re.IGNORECASE,
    ),
    "mismatch": re.compile(r"different at pc|\bmismatch\b|difftest.*fail", re.IGNORECASE),
    "assertion": re.compile(r"Assertion failed|\bassert(?:ion)?\b.*fail", re.IGNORECASE),
    "bad_trap": re.compile(r"HIT BAD TRAP|\bABORT\b", re.IGNORECASE),
    "good_trap": re.compile(r"HIT GOOD TRAP", re.IGNORECASE),
    "limit": re.compile(r"EXCEEDING CYCLE/INSTR LIMIT", re.IGNORECASE),
    "fatal": re.compile(r"\bfatal error\b|segmentation fault|core dumped", re.IGNORECASE),
}
FAILURE_TYPE_PRIORITY = (
    "stuck",
    "liveness",
    "mismatch",
    "assertion",
    "bad_trap",
    "fatal",
)
FAILURE_SIGNALS = set(FAILURE_TYPE_PRIORITY)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Run directories or log files")
    parser.add_argument(
        "--strict-instr",
        type=int,
        default=None,
        help="Minimum committed instructions required for a pass",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser.parse_args()


def discover_runs(paths: Iterable[Path]) -> list[Path]:
    found: set[Path] = set()
    artifact_names = OUT_NAMES + ERR_NAMES + ("exit-code",)
    for path in paths:
        if path.is_file() and path.name in artifact_names:
            found.add(path.resolve().parent)
        elif path.is_dir():
            for name in artifact_names:
                found.update(item.resolve().parent for item in path.rglob(name))
    return sorted(found)


def read_exit_code(run_dir: Path) -> int | None:
    path = run_dir / "exit-code"
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8", errors="replace").strip())
    except ValueError:
        return None


def matching_output_log(run_dir: Path) -> Path | None:
    for name in OUT_NAMES:
        path = run_dir / name
        if path.is_file():
            return path
    return None


def matching_error_log(run_dir: Path, out_path: Path | None) -> Path | None:
    preferred = {
        "simulator_out.txt": "simulator_err.txt",
        "simulation_out.txt": "simulation_err.txt",
        "stdout.log": "stderr.log",
    }.get(out_path.name if out_path else "", ERR_NAMES[0])
    candidates = (preferred,) + tuple(name for name in ERR_NAMES if name != preferred)
    for name in candidates:
        path = run_dir / name
        if path.is_file():
            return path
    return None


def scan_file(path: Path, state: dict) -> None:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for number, raw_line in enumerate(handle, 1):
            line = ANSI_RE.sub("", raw_line.rstrip())
            for match in INSTR_RE.finditer(line):
                state["max_instr"] = max(
                    state["max_instr"], int(match.group(1).replace(",", ""))
                )
            for name, pattern in SIGNALS.items():
                if pattern.search(line):
                    state["signals"].add(name)
                    state["evidence"].setdefault(
                        name, {"file": str(path), "line": number, "text": line[:500]}
                    )


def classify(exit_code: int | None, state: dict, strict_instr: int | None) -> str:
    if state["signals"] & FAILURE_SIGNALS:
        return "failed"
    if exit_code is not None and exit_code != 0:
        return "failed"
    if exit_code is None:
        return "incomplete"
    if strict_instr is not None:
        return "passed" if state["max_instr"] >= strict_instr else "insufficient-instr"
    if "good_trap" in state["signals"] or "limit" in state["signals"]:
        return "passed"
    return "inconclusive"


def failure_type(state: dict) -> str | None:
    for name in FAILURE_TYPE_PRIORITY:
        if name in state["signals"]:
            return name
    return None


def inspect_run(run_dir: Path, strict_instr: int | None) -> dict:
    out_path = matching_output_log(run_dir)
    err_path = matching_error_log(run_dir, out_path)
    state = {"max_instr": 0, "signals": set(), "evidence": {}}
    if out_path is not None:
        scan_file(out_path, state)
    if err_path is not None:
        scan_file(err_path, state)
    exit_code = read_exit_code(run_dir)
    return {
        "run_dir": str(run_dir),
        "stdout": str(out_path) if out_path else None,
        "stderr": str(err_path) if err_path else None,
        "exit_code": exit_code,
        "max_instr": state["max_instr"],
        "signals": sorted(state["signals"]),
        "failure_type": failure_type(state),
        "verdict": classify(exit_code, state, strict_instr),
        "evidence": state["evidence"],
    }


def print_text(results: list[dict]) -> None:
    for result in results:
        signals = ",".join(result["signals"]) or "none"
        primary = result["failure_type"] or "none"
        print(
            f"{result['verdict']}\texit={result['exit_code']}\t"
            f"instr={result['max_instr']}\ttype={primary}\t"
            f"signals={signals}\t{result['run_dir']}"
        )
        for name, evidence in result["evidence"].items():
            print(
                f"  {name}: {evidence['file']}:{evidence['line']}: "
                f"{evidence['text']}"
            )


def main() -> int:
    args = parse_args()
    runs = discover_runs(args.paths)
    results = [inspect_run(path, args.strict_instr) for path in runs]
    if args.format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=True))
    else:
        print_text(results)
    return 0 if runs else 2


if __name__ == "__main__":
    raise SystemExit(main())
