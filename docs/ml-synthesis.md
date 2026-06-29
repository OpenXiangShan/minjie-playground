# ML-Assisted Synthesis Research Plan

## Goal

Build a reproducible local research loop for machine-learning-assisted synthesis that can
improve FPGA compile efficiency and PPA for NutShell/MinJie flows. The first milestone is not
a trained model; it is a reliable trial dataset and worker harness for Vivado strategy search.

## Reference Routes

- AMD Vivado ML strategies predict implementation strategies that are likely to produce good
  results. AMD recommends running three suggested implementation strategies to guard against
  prediction error: <https://docs.amd.com/r/en-US/ug949-vivado-design-methodology/ML-Strategies>.
- AMD QoR Suggestions can generate or report suggestion objects after synthesis and write/apply
  RQS guidance for later runs: <https://docs.amd.com/r/en-US/ug906-vivado-design-analysis/Report-QoR-Suggestions>.
- OpenROAD AutoTuner models the open-source route: JSON parameter spaces, per-trial PPA
  metrics, and distributed search over Random/Grid/PBT/HyperOpt-style algorithms:
  <https://openroad-flow-scripts.readthedocs.io/en/latest/user/InstructionsForAutoTuner.html>.
- Ray Tune/HyperOpt are suitable later-stage execution/search engines once trial records are
  stable: <https://docs.ray.io/en/latest/tune/index.html> and <https://hyperopt.github.io/hyperopt/>.

The shared pattern is design-space optimization around tool parameters and feedback metrics,
not direct generation of RTL by a model.

## Repository Fit

The current FpgaDiff Vivado project flow already has the right control points:

- `env-scripts/fpga_diff/Makefile` creates projects, runs synthesis, and generates bitstreams.
- `env-scripts/fpga_diff/src/tcl/common/xs_uart.tcl` sets `synth_1` and `impl_1` strategies and
  directives.
- `env-scripts/fpga_diff/tools/gen_synth.tcl` and `gen_bitstream.tcl` run Vivado in batch mode.
- `env-scripts/fpga_diff/tools/generate_reports.tcl` can collect timing/utilization/route reports.
- `scripts/fpga_diff/run_incremental_experiment.sh` is the longer-term incremental-compile
  baseline for clean vs incremental runtime and reuse metrics.

`ml_synth/` is intentionally separate from these flows. It generates trial specs and applies
Vivado run properties after project creation, so default repository behavior remains unchanged.

## Phases

### Phase 0: Reproducible Data

Create a stable schema for every trial:

- commit/release path and RTL hash where available
- CPU/design/board/Vivado version/part
- strategy and directive settings
- worker host, jobs, start/end time, and return code
- stage runtime
- WNS/TNS, route status, utilization, bitstream path
- failure stage and error examples

This is implemented first in `ml_synth/scripts/schedule_trials.py`,
`run_trial.py`, `parse_vivado_reports.py`, and `rank_trials.py`.

### Phase 1: Non-ML Baselines

Run fixed Vivado strategy candidates:

- repo default
- Vivado defaults
- performance explore
- congestion-oriented run
- runtime-lean run

The acceptance criterion is comparable trial data, not immediate PPA gain.

### Phase 2: QoR Prediction

After enough trial records exist, train a simple classifier/ranker to predict:

- likely Vivado failure
- route completion
- timing-pass probability
- whether a trial is worth continuing after synthesis or placement

Start with lightweight tabular models. Do not add Optuna/Ray/sklearn until the trial records are
stable enough to justify the dependency.

### Phase 3: Active DSE

Use the predictor to choose the next batch of trials. Candidate controllers:

- random/grid search as a permanent baseline
- HyperOpt/TPE for tabular directive search
- Ray Tune when multi-host workers are stable

The target is fewer wasted Vivado runs per acceptable PPA result.

### Phase 4: Incremental And Partitioned Compile

Integrate the FpgaDiff incremental compile work once a matching NutShell release elaborates
cleanly. Whole-project incremental compile is the first proof point. CPU/DiffTest partitioned DCP
reuse comes after the SimTop/wrapper boundary is stable and a real CPU checkpoint boundary exists.

## Multi-Worker Execution

Use controller/worker separation:

- controller writes JSONL trial specs and owns the search space
- each worker consumes one spec
- every worker uses a unique `SUFFIX` and output directory
- workers never share a Vivado project
- runtime comparisons must record `jobs`, host, and failure stage

Do not over-subscribe Vivado licenses or CPU/memory. If a host is saturated, runtime data becomes
scheduler noise.

## Current Local Evidence

Validated so far:

- Vivado 2020.2 exists at `/nfs/home/fengkehan/tools/Xilinx/Vivado/2020.2/bin/vivado`.
- `ml_synth/` can generate deterministic trial specs and dry-run command plans.
- The parser is designed around existing Vivado `.time`, `runme.log`, `timing_summary.rpt`,
  `utilization.rpt`, and `route_status.rpt` shapes.

Known blocker for the current controlled NutShell sample:

- `SimTop_wrapper.sv` in `env-scripts/fpga_diff` does not match the sampled `SimTop.sv`.
  Vivado reports `SimTop` has 172 declared connections but the wrapper gives 79. This must be
  fixed or a matching release must be selected before claiming full NutShell bitstream success.

## Stop Conditions For Claims

Do not claim ML PPA improvement until all are true:

- same RTL/release and same Vivado version
- at least one baseline strategy and one candidate strategy
- complete timing/utilization/route/runtime records
- failed trials preserved
- no machine-load or license contention explains runtime differences
- bitstream/timing success validated for the winning candidate
