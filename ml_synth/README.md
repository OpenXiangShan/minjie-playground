# ML Synthesis Experiments

This directory contains the first reproducible loop for machine-learning-assisted FPGA
synthesis research in MinJie:

1. generate controlled Vivado strategy trials
2. run each trial in an isolated project suffix/output directory
3. collect timing/utilization/route/runtime reports
4. rank the results before adding any predictive model

The first phase is deliberately a DSE baseline, not a trained model. A model is only useful
after the repository has enough clean, comparable trial records.

## Current Scope

The initial target is the FpgaDiff Vivado project flow in `env-scripts/fpga_diff`.
The search space is limited to Vivado run strategies/directives and job counts while keeping
RTL, constraints, Vivado version, and target board fixed.

The intended metrics are:

- runtime per stage and total runtime
- trial status and failed stage
- post-route WNS/TNS when available
- LUT/FF/BRAM/URAM/DSP utilization
- route completion status
- bitstream path when generated

## Generate Trial Specs

```sh
python3 ml_synth/scripts/schedule_trials.py \
  --run-id smoke \
  --limit 2 \
  --out build/ml_synth/smoke/trials.jsonl
```

This writes worker-consumable JSONL specs. Each trial has a unique `SUFFIX`, so workers do
not share a Vivado project directory.

## Dry-Run One Trial

```sh
python3 ml_synth/scripts/run_trial.py \
  build/ml_synth/smoke/trials.jsonl \
  --trial-id smoke-0001
```

Dry-run mode writes `command_plan.sh` and prints the commands. It does not launch Vivado.

## Execute One Trial

```sh
python3 ml_synth/scripts/run_trial.py \
  build/ml_synth/smoke/trials.jsonl \
  --trial-id smoke-0001 \
  --execute
```

Set `NUTSHELL_BUILD_DIR` to override the default local NutShell build directory from
`configs/targets.nutshell.json`.

## Parse And Rank

```sh
python3 ml_synth/scripts/parse_vivado_reports.py \
  --trial-dir build/ml_synth/nutshell/smoke/mlsynth-smoke-0001-repo-default \
  --json-out build/ml_synth/nutshell/smoke/mlsynth-smoke-0001-repo-default/metrics.json

python3 ml_synth/scripts/rank_trials.py \
  build/ml_synth/nutshell/smoke \
  --csv-out build/ml_synth/nutshell/smoke/summary.csv
```

Failed trials stay in the dataset. They are negative labels for later QoR prediction and
worker scheduling.

## Worker Contract

- One worker owns one trial spec.
- One trial uses one unique `SUFFIX` and one output directory.
- Workers do not edit the search space.
- Workers append/emit only trial-local data; a controller merges and ranks results.
- Keep external Vivado concurrency below the available license/CPU/memory capacity, otherwise
  runtime comparisons measure machine contention instead of strategy quality.

## Known Local Issue

The current `current-nutshell` controlled sample used for the FpgaDiff incremental experiment
does not elaborate with the current `env-scripts/fpga_diff/src/rtl/nutshell/SimTop_wrapper.sv`:
Vivado reports that `SimTop` declares 172 connections while the wrapper provides 79. Use a
matching NutShell release/build before claiming full timing or bitstream success for this target.
