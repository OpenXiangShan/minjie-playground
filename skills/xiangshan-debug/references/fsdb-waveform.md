# FSDB Extraction

Use this reference for existing FSDB input. Extract a narrow time and signal selection with compatible
Verdi tools, then convert the VCD to FST for [pywellen queries](waveform.md). Keep the original FSDB,
its simulator or RTL/FPGA build, commit/config, and associated log. Conversion extracts evidence; it
neither reruns the design nor proves Verilator reproduction. Without build provenance, report only
waveform facts.

Store exports of supplied input in `original/analysis/fsdb-export/`. Exports from baseline or fixed
runs belong in that run's analysis directory.

## 1. Select tools and host

Tools may run locally or remotely. The SSH examples use `fsdb_host` and optional space-separated
`fsdb_modules`; leave the latter empty when the tools are already on `PATH`.

```bash
: "${fsdb_host:?Set the host with the FSDB tools}"
fsdb_modules=${fsdb_modules:-}
ssh -o BatchMode=yes -o ConnectTimeout=15 "$fsdb_host" \
  "bash -l -s -- '$fsdb_modules'" <<'REMOTE'
set -euo pipefail
export LC_ALL=C
if [[ -n "$1" ]]; then
  type module
  read -r -a fsdb_tool_modules <<< "$1"
  module load "${fsdb_tool_modules[@]}"
  module list 2>&1
fi
command -v fsdb2vcd vcd2fst
REMOTE
```

Use available host and tool versions, and record them. A login shell loads the environment needed for
`module`; `LC_ALL=C` avoids locale warnings. An older FSDB-format warning alone does not imply failure:
check the exit status and exported data.

Replace example paths, scopes, and times. Run local examples in the same shell to retain their variables.
These SSH commands quote paths and module names with single quotes; adapt the quoting if values contain
single quotes.

## 2. Check input and output access

Check shared storage before copying a large input:

```bash
fsdb_input=/shared/project/waves.fsdb
fsdb_remote_input="$fsdb_input"
ls -lh "$fsdb_input"
ssh "$fsdb_host" "bash -s -- '$fsdb_remote_input'" <<'REMOTE'
set -euo pipefail
test -r "$1"
ls -lh "$1"
df -T "$1"
REMOTE
```

If shared access fails, stage the input once, compare checksums, and reuse that copy:

```bash
fsdb_remote_dir=$(ssh "$fsdb_host" 'mktemp -d /tmp/fsdb-work-XXXXXXXX')
fsdb_remote_input="$fsdb_remote_dir/waves.fsdb"
scp "$fsdb_input" "${fsdb_host}:$fsdb_remote_input"
sha256sum "$fsdb_input"
ssh "$fsdb_host" "sha256sum '$fsdb_remote_input'"
```

Choose the output location independently. It can be writable shared storage or remote scratch for large
intermediate VCDs. For shared output:

```bash
fsdb_remote_dir=/shared/project/original/analysis/fsdb-export
ssh "$fsdb_host" "mkdir -p '$fsdb_remote_dir' && df -h '$fsdb_remote_dir'"
```

Record both paths. Preserve the original input outside temporary storage. Hash a large source once when
needed, rather than reading it again for every export.

## 3. Inspect metadata

Read the summary before selecting a window:

```bash
ssh "$fsdb_host" "bash -l -s -- '$fsdb_remote_dir' '$fsdb_remote_input' '$fsdb_modules'" <<'REMOTE'
set -euo pipefail
export LC_ALL=C
if [[ -n "$3" ]]; then
  read -r -a fsdb_tool_modules <<< "$3"
  module load "${fsdb_tool_modules[@]}"
fi
cd "$1"
fsdb2vcd "$2" -summary >input.summary.txt 2>&1
cat input.summary.txt
REMOTE
```

Check the time unit, minimum/maximum time tags, variable count, format and simulator versions,
creation date, and completion status. Summary ticks are not necessarily nanoseconds; use explicit units
such as `800us` in export arguments. A compressed FSDB can expand to a much larger text VCD.

## 4. Export a narrow window

Filter both time and signals. Start with relevant clocks, reset, interfaces, handshakes, IDs, addresses,
and responses. Increase depth only for a small subtree; select individual signals when arrays are large.
Give each scope an explicit `-level`, a depth bound rather than unlimited recursion. Quote names with
brackets. Confirm option behavior with the installed tool version.

```bash
ssh "$fsdb_host" "bash -l -s -- '$fsdb_remote_dir' '$fsdb_remote_input' '$fsdb_modules'" <<'REMOTE'
set -euo pipefail
export LC_ALL=C
if [[ -n "$3" ]]; then
  read -r -a fsdb_tool_modules <<< "$3"
  module load "${fsdb_tool_modules[@]}"
fi
cd "$1"
wave_input="$2"
wave_prefix=focus-800-810
wave_begin=800us
wave_end=810us
if [[ -e "$wave_prefix.vcd" || -e "$wave_prefix.fst" ]]; then
  printf 'Outputs exist; choose a new prefix: %s\n' "$wave_prefix" >&2
  exit 1
fi
filter_args=(-s '/tb/clk' '/tb/rst_n'
  '/tb/dut/target' -level 1
  '/tb/dut/target/internal' -level 2)
convert_args=(fsdb2vcd "$wave_input" -o "$wave_prefix.vcd"
  -bt "$wave_begin" -et "$wave_end" -keep_last_time "${filter_args[@]}")
{
  printf '%q ' "${convert_args[@]}"
  printf '\n'
  printf '%q ' vcd2fst -p "$wave_prefix.vcd" "$wave_prefix.fst"
  printf '\n'
} >"$wave_prefix.command.txt"
fsdb2vcd "$wave_input" -summary >"$wave_prefix.summary.txt" 2>&1
"${convert_args[@]}" >"$wave_prefix.fsdb2vcd.log" 2>&1
test -s "$wave_prefix.vcd"
vcd2fst -p "$wave_prefix.vcd" "$wave_prefix.fst" >"$wave_prefix.vcd2fst.log" 2>&1
test -s "$wave_prefix.fst"
sha256sum "$wave_prefix.fst" >"$wave_prefix.SHA256SUMS"
REMOTE
```

Bash arrays preserve argument boundaries; the quoted heredoc prevents local expansion. Remote arguments
provide the output directory, input path, and optional modules. Windowed exports usually preserve absolute
time and include initial values at the window start; verify this for the installed tool and input.
Those initial values are not necessarily transitions. VCD/FST preserves selected RTL signals, not FSDB
UVM transaction records.

For large inputs, narrow time and signal scope together. Overlap segments when a transaction crosses a
boundary. Each export reparses the source, so avoid excessive segmentation. Monitor disk space, output
size, logs, and the conversion process's memory use. If needed, stop only the confirmed conversion process
and retry with a smaller selection and a new prefix.

## 5. Validate and transfer

Wait for both conversion stages to finish. Check timescale, window boundaries, final time tag, and required
internal signals. A non-empty file and successful exit do not establish a complete selection. Compare
representative values at the same times in overlapping exports.

Shared outputs need no transfer. For remote scratch, copy the completed FST and all records; the large
intermediate VCD may stay remotely:

```bash
fsdb_prefix=focus-800-810
fsdb_local_export=/absolute/path/to/task/original/analysis/fsdb-export
mkdir -p "$fsdb_local_export"
scp "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.fst" "$fsdb_local_export/"
scp "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.command.txt" \
  "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.summary.txt" \
  "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.fsdb2vcd.log" \
  "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.vcd2fst.log" \
  "${fsdb_host}:$fsdb_remote_dir/$fsdb_prefix.SHA256SUMS" "$fsdb_local_export/"
(cd "$fsdb_local_export" && sha256sum -c "$fsdb_prefix.SHA256SUMS")
```

Retain tool versions, input/output paths, commands, windows, scopes, depth, logs, and checksums so the
extraction can be repeated. If a required signal is absent, check both the selection and whether the
source recorded it; conversion cannot recover unrecorded signals.
