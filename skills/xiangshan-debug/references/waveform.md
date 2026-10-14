# VCD/FST Waveform Analysis

This reference analyzes an existing VCD or FST; it does not run a simulation. For FSDB, first follow
[fsdb-waveform.md](fsdb-waveform.md), then query the exported VCD/FST with `pywellen`. Match waveform,
logs, RTL, source commit, and configuration before drawing causal conclusions. `pywellen` reads VCD/FST
directly; no additional waveform CLI, cache, or RTL parser is required.

## 1. Record the input

Keep the waveform, associated failure log, source tree, and optional generated RTL from the same build.
Store baseline queries in `reproduction/analysis/`, supplied-scene queries in `original/analysis/`, and
fixed-run queries in that run's `analysis/` directory. Record pywellen version, file format, timescale,
time range, and the method used to align waveform time with log events. Keep generated queries outside
the installed skill. Without matching generated RTL, report waveform observations without claiming an
exact mapping to RTL internals.

All paths, signal names, and times below are examples; replace them with values from the current input.

```bash
python3 - <<'PY'
import importlib.metadata
import pywellen

print("pywellen:", importlib.metadata.version("pywellen"))
wave = pywellen.Waveform("/absolute/path/to/wave.fst", multi_threaded=True)
print("format:", wave.file_format, "timescale:", wave.timescale)
PY
```

A fork or checkpoint waveform may start at a different time origin. Use a known clock, commit, valid, or
error signal to calibrate it; do not equate its start time with difftest `cycleCnt`.

## 2. Find candidate signals

Large designs may contain millions of variables. Filter one pass by names derived from the current log and
source, keep a bounded candidate file, and record scan and truncation counts. Do not save the full signal
list or construct a full name set merely to find a few signals.

```bash
WAVE=/absolute/path/to/wave.vcd
ANALYSIS=/absolute/path/to/analysis
mkdir -p "$ANALYSIS"

: "${SIGNAL_TOKENS:?Set comma-separated keywords from the relevant module or fields}"
WAVE="$WAVE" SIGNAL_TOKENS="$SIGNAL_TOKENS" OUT="$ANALYSIS/signal-candidates.txt" python3 - <<'PY'
import os
from pathlib import Path
import pywellen

tokens = tuple(x.strip().lower() for x in os.environ["SIGNAL_TOKENS"].split(",") if x.strip())
if not tokens:
    raise SystemExit("SIGNAL_TOKENS must contain a keyword")
wave = pywellen.Waveform(path=os.environ["WAVE"], remove_scopes_with_empty_name=False)
max_matches = 5000
scanned = matched = 0
matches = []
for var in wave.all_vars():
    scanned += 1
    if any(token in var.full_name.lower() for token in tokens):
        matched += 1
        if len(matches) < max_matches:
            matches.append(f"{var.full_name}\twidth={var.bitwidth}\tsignal_id={var.signal_id}")
truncated = matched > len(matches)
header = (
    f"scanned={scanned} matched={matched} saved={len(matches)} "
    f"max_matches={max_matches} truncated={truncated} tokens={','.join(tokens)}"
)
Path(os.environ["OUT"]).write_text(header + "\n" + "\n".join(matches) + "\n", encoding="utf-8")
print(header)
PY
```

If the candidate set is too broad, narrow the hierarchy or field tokens. If it is empty, widen the filter
one step at a time and record why. Signal paths must be confirmed from the waveform and matching source;
do not infer them from module names alone.

## 3. Query a point or window

```bash
WAVE=/absolute/path/to/wave.fst OUT=/absolute/path/to/value.json python3 - <<'PY'
import json
import os
from pathlib import Path
import pywellen

name = "TOP.SimTop.cpu.core.rob.commit_valid"
time = 129500
wave = pywellen.Waveform(path=os.environ["WAVE"], remove_scopes_with_empty_name=False)
var = next((x for x in wave.all_vars() if x.full_name == name), None)
if var is None:
    raise SystemExit(f"signal not found: {name}")
result = {"signal": name, "time": time, "value": var.signal.value_at(time)}
Path(os.environ["OUT"]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(result)
PY
```

For a window, resolve names to `Var` objects and pass them to `stream_changes`. Map callback signal IDs
back to their full names; use a window small enough to distinguish the candidate cause.

```bash
WAVE="$WAVE" OUT="$ANALYSIS/changes-window.json" python3 - <<'PY'
import json
import os
from pathlib import Path
import pywellen

signals = [
    "TOP.SimTop.cpu.core.rob.commit_valid",
    "TOP.SimTop.cpu.core.rob.commit_pc",
]
start, end = 125000, 126000
wave = pywellen.Waveform(
    path=os.environ["WAVE"], multi_threaded=True, remove_scopes_with_empty_name=False
)
wanted = set(signals)
selected = {}
for var in wave.all_vars():
    if var.full_name in wanted:
        selected[var.full_name] = var
missing = wanted - selected.keys()
if missing:
    raise SystemExit(f"signals not found: {sorted(missing)}")
names_by_id = {str(var.signal_id): name for name, var in selected.items()}
changes = []

def collect(time, signal_id, value):
    if start <= time <= end:
        changes.append({"time": time, "signal_id": str(signal_id), "value": value})

wave.stream_changes(collect, list(selected.values()))
result = {"start": start, "end": end, "signals": names_by_id, "changes": changes}
Path(os.environ["OUT"]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(f"changes: {len(changes)}")
PY
```

Confirm signal meaning against matching RTL and Chisel source. A name match alone does not establish
source ownership.

At each relevant boundary, inspect the signals that establish progress or a transaction: valid/ready/fire,
backpressure, allocation/free, arbitration, IDs, addresses, requests, responses, state transitions,
redirects, flushes, and commit. Select the smallest set for the failure type; do not require a fixed list
of module names or fields.

Classify every conclusion as a waveform fact, source meaning, candidate cause, or verified fix. If baseline
Verilator does not reproduce the reported failure, report “not reproduced/insufficient evidence”; a clean
fixed exit alone is not proof.

## Common issues

- Missing or empty waveform: stop and record the missing input.
- Missing `pywellen`: enable it in the current Python environment, record the import error, and do not
  invent signal values.
- Missing signal path: use a bounded keyword scan and refine it gradually.
- Mismatched waveform and RTL/source commit: stop and select matching artifacts.
- FSDB input: convert and checksum the selected export before querying it.
