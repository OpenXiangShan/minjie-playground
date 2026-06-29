#!/usr/bin/env python3
"""Run or dry-run one ML synthesis Vivado trial."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]


def load_spec(path: Path, trial_id: str | None) -> dict:
    if path.suffix == ".jsonl":
        with path.open() as f:
            for line in f:
                if not line.strip():
                    continue
                spec = json.loads(line)
                if trial_id is None or spec.get("trial_id") == trial_id:
                    return spec
        raise SystemExit(f"ERROR: trial_id not found in {path}: {trial_id}")
    return json.loads(path.read_text(errors="replace"))


def discover_vivado() -> str:
    env_vivado = os.environ.get("VIVADO", "")
    if env_vivado and Path(env_vivado).exists():
        return env_vivado
    path_vivado = shutil.which("vivado")
    if path_vivado:
        return path_vivado
    finder = REPO_ROOT / "scripts/fpga_diff/find_vivado.sh"
    if finder.is_file():
        proc = subprocess.run(
            [str(finder)],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode == 0:
            candidate = proc.stdout.strip().splitlines()[-1]
            if candidate:
                return candidate
    raise SystemExit("ERROR: vivado not found. Set VIVADO=/path/to/vivado.")


def strategy_assignments(strategy: dict) -> list[str]:
    mapping = {
        "synth_strategy": "synth_1.strategy",
        "synth_directive": "synth_1.steps.synth_design.args.directive",
        "synth_gated_clock_conversion": "synth_1.steps.synth_design.args.gated_clock_conversion",
        "synth_bufg": "synth_1.steps.synth_design.args.bufg",
        "impl_strategy": "impl_1.strategy",
        "place_directive": "impl_1.steps.place_design.args.directive",
        "phys_opt_directive": "impl_1.steps.phys_opt_design.args.directive",
        "route_directive": "impl_1.steps.route_design.args.directive",
    }
    result = []
    for key, prop in mapping.items():
        value = strategy.get(key)
        if value not in (None, ""):
            result.append(f"{prop}={value}")
    return result


def command_plan(spec: dict, vivado: str) -> list[tuple[str, list[str]]]:
    flow_dir = REPO_ROOT / spec["flow_dir"]
    cpu = spec["cpu"]
    suffix = spec["suffix"]
    jobs = str(spec.get("jobs", 1))
    core_dir = os.environ.get(spec.get("core_dir_env", ""), spec.get("core_dir", ""))
    prj_name = f"fpga_{cpu}-{suffix}"
    xpr = flow_dir / prj_name / f"{prj_name}.xpr"
    report_dir = (REPO_ROOT / spec["output_dir"]).resolve() / "reports"

    make_env_args = [f"CPU={cpu}", f"SUFFIX={suffix}", f"VIVADO_JOBS={jobs}"]
    if core_dir:
        make_env_args.append(f"CORE_DIR={core_dir}")

    return [
        (
            "project",
            [
                "make",
                "-C",
                str(flow_dir),
                spec.get("make_project_target", "all"),
                *make_env_args,
            ],
        ),
        (
            "apply-strategy",
            [
                vivado,
                "-mode",
                "batch",
                "-source",
                str(REPO_ROOT / "ml_synth/tcl/apply_strategy.tcl"),
                "-tclargs",
                str(xpr),
                *strategy_assignments(spec.get("strategy", {})),
            ],
        ),
        (
            "synth",
            [
                "make",
                "-C",
                str(flow_dir),
                spec.get("make_synth_target", "synth"),
                f"CPU={cpu}",
                f"SUFFIX={suffix}",
                f"VIVADO_JOBS={jobs}",
            ],
        ),
        (
            "bitstream",
            [
                "make",
                "-C",
                str(flow_dir),
                spec.get("make_bitstream_target", "bitstream"),
                f"CPU={cpu}",
                f"SUFFIX={suffix}",
                f"VIVADO_JOBS={jobs}",
            ],
        ),
        (
            "collect-metrics",
            [
                vivado,
                "-mode",
                "batch",
                "-source",
                str(REPO_ROOT / "ml_synth/tcl/collect_metrics.tcl"),
                "-tclargs",
                str(xpr),
                str(report_dir),
                "impl_1",
            ],
        ),
        (
            "parse-reports",
            [
                sys.executable,
                str(REPO_ROOT / "ml_synth/scripts/parse_vivado_reports.py"),
                "--trial-dir",
                str(Path(spec["output_dir"])),
                "--json-out",
                str(Path(spec["output_dir"]) / "metrics.json"),
            ],
        ),
    ]


def quote_command(cmd: Iterable[str]) -> str:
    return " ".join(subprocess.list2cmdline([part]) for part in cmd)


def run_step(
    label: str,
    cmd: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_dir: Path,
) -> int:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{label}.log"
    time_path = log_dir / f"{label}.time"
    start = time.monotonic()
    with log_path.open("w") as log:
        log.write(f"$ {quote_command(cmd)}\n")
        log.flush()
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    elapsed = time.monotonic() - start
    time_path.write_text(f"elapsed_sec={elapsed:.3f}\nreturncode={proc.returncode}\n")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or dry-run one Vivado DSE trial.")
    parser.add_argument("spec", help="Trial spec JSON or JSONL")
    parser.add_argument("--trial-id", help="Trial ID when reading JSONL")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run commands. Default only writes command plan.",
    )
    parser.add_argument(
        "--stop-after",
        choices=["project", "apply-strategy", "synth", "bitstream", "collect-metrics", "parse-reports"],
        help="Stop after this step",
    )
    args = parser.parse_args()

    spec = load_spec(REPO_ROOT / args.spec, args.trial_id)
    out_dir = REPO_ROOT / spec["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "config.json").write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")

    vivado = discover_vivado()
    env = os.environ.copy()
    env["PATH"] = f"{Path(vivado).parent}:{env.get('PATH', '')}"
    env["VIVADO"] = vivado

    plan = command_plan(spec, vivado)
    plan_path = out_dir / "command_plan.sh"
    plan_path.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        + "\n".join(quote_command(cmd) for _, cmd in plan)
        + "\n"
    )
    print(f"trial: {spec.get('trial_id')} {spec.get('strategy_name')}")
    print(f"output: {out_dir}")
    print(f"plan: {plan_path}")

    if not args.execute:
        for label, cmd in plan:
            print(f"[dry-run:{label}] {quote_command(cmd)}")
        return 0

    log_dir = out_dir / "logs"
    for label, cmd in plan:
        rc = run_step(label, cmd, cwd=REPO_ROOT, env=env, log_dir=log_dir)
        if rc != 0:
            failure = {"failed_step": label, "returncode": rc}
            (out_dir / "failure.json").write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n"
            )
            print(f"ERROR: {label} failed with return code {rc}; see {log_dir / (label + '.log')}")
            return rc
        if args.stop_after == label:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
