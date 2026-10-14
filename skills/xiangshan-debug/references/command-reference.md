# Command Templates and Artifact Checks

Use these templates as starting points, then confirm option names against the current XiangShan commit,
Makefile, and emu `--help`. The workflow and verdicts are defined in [SKILL.md](../SKILL.md).

This skill builds and runs only Verilator. Existing gsim artifacts are input provenance, never debug,
reproduction, or fixed emulators. Redact credentials in logs; do not archive a raw `env` output.

## Triage

```bash
XIANGSHAN_DEBUG_SKILL_ROOT=/path/to/xiangshan-debug
python3 "$XIANGSHAN_DEBUG_SKILL_ROOT/scripts/triage_logs.py" \
  --format text /path/to/run-or-archive

rg -n -i 'different at pc|mismatch|assert|abort|bad trap|leak|fatal|core .*instrCnt' \
  /path/to/simulator_out.txt /path/to/simulator_err.txt
```

`triage_logs.py` reports candidate types, signals, maximum `instrCnt`, exit codes, and evidence lines.
It does not decide whether assertion messages belong to one case; verify the original context manually.

## Build a debug emu

Run `make init` before the first build, verify dependencies, then freeze the source tree. Save build output
in the task-level `build-log/` directory.

```bash
export NOOP_HOME=/absolute/path/to/task/XiangShan-original
mkdir -p original build-log
make -C "$NOOP_HOME" init >original/source-init.log 2>&1
INIT_STATUS=$?
printf '%s\n' "$INIT_STATUS" >original/source-init.exit-code
test "$INIT_STATUS" -eq 0 || exit "$INIT_STATUS"

: "${BUILD_JOBS:?Set compiler parallelism for this host}"
make -C "$NOOP_HOME" emu EMU_TRACE=1 WITH_CHISELDB=1 -j"$BUILD_JOBS" \
  >build-log/build-debug.log 2>&1
BUILD_STATUS=$?
printf 'debug emu build exit code: %s\n' "$BUILD_STATUS"
test "$BUILD_STATUS" -eq 0 || exit "$BUILD_STATUS"

EMU_REAL=$(readlink -f "$NOOP_HOME/build/emu")
test -x "$EMU_REAL"
stat "$EMU_REAL"
sha256sum "$EMU_REAL"
"$EMU_REAL" --help
```

Use the current commit's actual waveform, ChiselDB, DRAMSim3, Constantin, configuration, and thread
options. Verify that generated FIR/RTL, C++ model, object files, and final emu use the same source and
configuration. If the final target is gsim, stop and record a configuration error. Clean only generated
files shown to be invalid.

Build the fixed emu with the same configuration after switching `NOOP_HOME` to the private `XiangShan/`
tree. Save output in `build-log/build-fixed.log`; never modify the frozen baseline tree.

## Run one checkpoint

The wrapper below uses an explicit execution budget. Set `RUN_LIMIT_KIND=instr` or `cycle`; record the
selected limit and rationale in `execution.md`.

```sh
#!/bin/sh
set -u
: "${NOOP_HOME:?Set NOOP_HOME to the XiangShan root}"
: "${EMU:?Set EMU to the copied Verilator emu}"
: "${CHECKPOINT:?Set CHECKPOINT to the checkpoint}"
: "${NEMU:?Set NEMU to the matching reference-model library}"
: "${RUN_LIMIT:?Set the execution budget}"
: "${RUN_DIR:?Set RUN_DIR to the run artifact directory}"

RUN_LIMIT_KIND=${RUN_LIMIT_KIND:-instr}
case "$RUN_LIMIT_KIND" in
  instr) set -- -I "$RUN_LIMIT" ;;
  cycle) set -- -C "$RUN_LIMIT" ;;
  *) printf 'Invalid RUN_LIMIT_KIND: %s\n' "$RUN_LIMIT_KIND" >&2; exit 2 ;;
esac
mkdir -p "$RUN_DIR"
"$EMU" -i "$CHECKPOINT" --diff "$NEMU" --enable-fork "$@" \
  >"$RUN_DIR/simulator_out.txt" \
  2>"$RUN_DIR/simulator_err.txt"
EMU_STATUS=$?
printf '%s\n' "$EMU_STATUS" >"$RUN_DIR/exit-code"
printf 'emu exit code: %s\n' "$EMU_STATUS"
exit "$EMU_STATUS"
```

Logs, exit status, and waveform must come from the same invocation. Stream output directly to files; do not
accumulate multi-gigabyte output in a Python pipe. If a fork child writes the waveform, wait for it to
finish and select only a new, non-empty file from this run. Resolve mutable emu symlinks before archiving
and record the binary digest.

Check the current emu's fork behavior in its parameter and child initialization code. A parent that
disables its own waveform may still enable it in a failure-triggered child. Use `--enable-fork` only
when that run produces the required waveform; otherwise select the supported non-fork mode.

Choose a margin such as `RUN_MARGIN=10000` only when it represents the required observation window. A
known error count or cycle plus this margin gives the execution limit; use `-C` when only the cycle is
known. For unknown positions, choose and record a separate budget. A normal baseline limit without the
first error is “not reproduced.” Each retry must state its hypothesis, parameter difference, expected
result, and stopping condition. Stop at the planned budget or when no new evidence justifies a retry.

## Patch checks

```bash
: "${BASE_COMMIT:?Set the recorded baseline commit}"
git -C /path/to/task/XiangShan diff --check
git -C /path/to/task/XiangShan diff --binary "$BASE_COMMIT" -- \
  >/path/to/task/patch/patch.diff
```

For modified submodules, create a separate patch and record patch application order in `message.txt`.
