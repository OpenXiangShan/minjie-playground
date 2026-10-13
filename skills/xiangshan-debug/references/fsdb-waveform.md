# FSDB Waveform Processing

This reference extends [SKILL.md](../SKILL.md) with analysis of existing FSDB inputs. Read it when a supplied waveform is FSDB; use [waveform.md](waveform.md) for VCD/FST inspection and `pywellen` queries after conversion.

For supplied failure-scene inputs, retain the original waveform path and identity and place completed exports and conversion records in `original/analysis/fsdb-export/` under the task root. For waveforms from a recorded baseline or fixed run, keep the exports within that run's analysis directory. Record the original simulator or FPGA/RTL build, commit/config, log association, and whether these match the source being analyzed. Conversion does not rerun the design or prove that Verilator reproduced the failure. If build provenance is missing, record the gap and limit conclusions to waveform facts.

Use `eda01` to extract selected times and signals from an FSDB into VCD, then convert it to FST.
Reduce the selection before exporting large waveforms. Keep the original FSDB for later extraction.

SSH provides access to the conversion tools; it does not imply that files must be copied.
Shared NFS may expose the same absolute paths on the local machine and `eda01`; verify this for the current task.
Check input and output access separately: a shared FSDB can be read directly while
intermediate files are written to scratch space on `eda01`.

Replace example paths, `/tb/...` scopes, and time windows with actual values.
Run local examples in the same shell so their variables remain available.

## 1. Load the tools on eda01

The default noninteractive SSH shell on `eda01` may not initialize `module`.
Use a Bash login shell:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 eda01 'bash -l -s' <<'REMOTE'
set -euo pipefail
export LC_ALL=C
type module
module load synopsys/vcs/Q-2020.03-SP2 synopsys/verdi/V-2023.12-SP1-1
module list 2>&1
command -v fsdb2vcd vcd2fst
REMOTE
```

The tools used here are Verdi's `fsdb2vcd` and `/usr/bin/vcd2fst`.
`LC_ALL=C` avoids unsupported-locale warnings. If these module versions are unavailable,
use `module avail` in the login shell and record the versions selected.
The loaded VCS version need not match the simulator that generated the FSDB.

For format compatibility issues, inspect the log and Verdi version. An older-format warning
does not necessarily mean failure; check exit status, errors, and exported data.

## 2. Check shared storage before copying

### Input already accessible on eda01

For an input on shared NFS, use the same absolute path on both machines.
Check that `eda01` can read it:

```bash
fsdb_input=/shared/project/waves.fsdb
fsdb_remote_input="$fsdb_input"
ls -lh "$fsdb_input"
ssh eda01 "bash -s -- '$fsdb_remote_input'" <<'REMOTE'
set -euo pipefail
test -r "$1"
ls -lh "$1"
df -T "$1"
REMOTE
```

Record the file size and waveform metadata. If a checksum is needed for reproducibility,
calculate it once: hashing a large input reads the whole file, so avoid repeating it for
every export.

If shared access works, use `fsdb_remote_input` directly. No input copy is needed.

### Input not accessible on eda01

Only when shared access is unavailable, stage a copy in a scratch directory:

```bash
fsdb_input=/local/path/waves.fsdb
fsdb_remote_dir=$(ssh eda01 'mktemp -d /tmp/fsdb-work-XXXXXXXX')
fsdb_remote_input="$fsdb_remote_dir/waves.fsdb"
scp "$fsdb_input" "eda01:$fsdb_remote_input"
sha256sum "$fsdb_input"
ssh eda01 "sha256sum '$fsdb_remote_input'"
```

Compare checksums and reuse the staged file for later exports. Keep the original elsewhere:
`/tmp` may be cleaned.

### Choose the output directory independently

To make outputs directly accessible from both machines, use writable shared storage:

```bash
fsdb_remote_dir=/shared/project/original/analysis/fsdb-export
ssh eda01 "mkdir -p '$fsdb_remote_dir'"
ssh eda01 "df -h '$fsdb_remote_dir'"
```

Alternatively, use remote scratch space to keep large intermediate VCD files off NFS:

```bash
fsdb_remote_dir=$(ssh eda01 'mktemp -d /tmp/fsdb-work-XXXXXXXX')
ssh eda01 "df -h '$fsdb_remote_dir'"
```

A scratch directory already created for input staging can also hold outputs.
`fsdb_remote_input` remains the absolute input path, independent of the output directory.
Record both paths.

These SSH examples embed paths inside single quotes. Use paths without embedded single
quotes, or adapt the shell escaping when such paths are required.

## 3. Inspect FSDB metadata

Read a summary before extracting signal changes:

```bash
ssh eda01 "bash -l -s -- '$fsdb_remote_dir' '$fsdb_remote_input'" <<'REMOTE'
set -euo pipefail
export LC_ALL=C
module load synopsys/vcs/Q-2020.03-SP2 synopsys/verdi/V-2023.12-SP1-1
cd "$1"
fsdb2vcd "$2" -summary > input.summary.txt 2>&1
cat input.summary.txt
REMOTE
```

Check `scale unit`, `min/max xtag`, `unique var count`, format version, simulator version,
creation date, and whether the file finished normally.

For example, `81610500` ticks at `10ps` correspond to `816105ns`.
Summary ticks are not automatically nanoseconds. Specify units explicitly in export
arguments, such as `-bt 800us -et 810us`.

FSDB is compressed. A few hundred MiB may contain millions of signals or large memory
arrays. Expanding it to text VCD can consume much more disk space and memory.

## 4. Select both time and signal scope

| Option | Purpose |
| --- | --- |
| `-bt/-et` | Start and end times with explicit units |
| `-s` | Signals or scopes, using FSDB paths separated by `/` |
| `-level 1` | Direct signals of the selected scope with the Verdi version above |
| `-level 2` | A shallow selection including the next level |
| `-level 99` | Deep extraction of a small subtree; a depth bound, not unlimited recursion |
| `-keep_last_time` | Preserve the export's final time tag |

Place an explicit `-level` after each scope. Avoid relying on omitted depth values or
neighboring selections. Quote names containing brackets, such as `core[0]`, to prevent globbing.

Start with clocks, resets, target interfaces, and adjacent stages. Include valid/ready or
enables, addresses, IDs, and responses needed to interpret the interface. Preserve relevant
clocks when correlating multiple clock domains.

Increase depth only for small subtrees whose internal state is needed. Even a shallow scope
can contain large arrays; select individual signals in that case. Exported interface signals
do not prove that internal submodules were included.

## 5. Export VCD and convert it to FST

Run from the local shell after setting the input and output paths. Replace scopes and times,
and use a new output prefix for each export:

```bash
ssh eda01 "bash -l -s -- '$fsdb_remote_dir' '$fsdb_remote_input'" <<'REMOTE'
set -euo pipefail
export LC_ALL=C
module load synopsys/vcs/Q-2020.03-SP2 synopsys/verdi/V-2023.12-SP1-1
cd "$1"
wave_input="$2"

wave_prefix=focus-800-810
wave_begin=800us
wave_end=810us
if [[ -e "$wave_prefix.vcd" || -e "$wave_prefix.fst" ]]; then
    printf 'Outputs exist; choose a new wave_prefix: %s\n' "$wave_prefix" >&2
    exit 1
fi
filter_args=(-s '/tb/clk' '/tb/rst_n'
    '/tb/dut/target' -level 1
    '/tb/dut/target/regs' -level 99)
convert_args=(fsdb2vcd "$wave_input" -o "$wave_prefix.vcd"
    -bt "$wave_begin" -et "$wave_end" -keep_last_time "${filter_args[@]}")

{
    printf '%q ' "${convert_args[@]}"
    printf '\n'
    printf '%q ' vcd2fst -p "$wave_prefix.vcd" "$wave_prefix.fst"
    printf '\n'
} > "$wave_prefix.command.txt"
fsdb2vcd "$wave_input" -summary > "$wave_prefix.summary.txt" 2>&1
"${convert_args[@]}" > "$wave_prefix.fsdb2vcd.log" 2>&1
test -s "$wave_prefix.vcd"
vcd2fst -p "$wave_prefix.vcd" "$wave_prefix.fst" > "$wave_prefix.vcd2fst.log" 2>&1
test -s "$wave_prefix.fst"
sha256sum "$wave_prefix.fst" > "$wave_prefix.SHA256SUMS"
REMOTE
```

Bash arrays preserve argument boundaries. The quoted heredoc prevents local expansion of
script variables; `$1` and `$2` are the paths passed to remote Bash. `vcd2fst -p` enables
parallel conversion. Local variables are not otherwise automatically available over SSH.

Windowed exports generally preserve absolute times and provide initial states at the window
start. Verify this behavior with the actual tool version and input. This VCD/FST path exports
selected RTL signals and does not preserve FSDB UVM transaction recording.

## 6. Handle large waveforms

### Reduce data during extraction

Use time and signal filters together. A short window may still expand huge arrays and
hierarchy declarations; a small scope may still contain long signal histories.

1. Use simulation logs to select a broad problem window and a few relevant interfaces.
2. Locate the event, then shorten the window.
3. Add depth only for internal submodules needed to explain it.
4. Replace array-heavy scopes with explicit signal selections.

Filtering a completed VCD does not reduce its original export cost. FST compression also
does not avoid the disk and memory cost of generating a full VCD.

### Split long time ranges

Inside a remote shell with tools loaded, set `wave_input` to the absolute path on `eda01`
and export successive windows with the same signal selection:

```bash
wave_input=/shared/project/waves.fsdb
fsdb2vcd "$wave_input" -o segment-800-805.vcd -bt 800us -et 805us -keep_last_time \
  -s '/tb/clk' '/tb/dut/target' -level 1
vcd2fst -p segment-800-805.vcd segment-800-805.fst

fsdb2vcd "$wave_input" -o segment-805-810.vcd -bt 805us -et 810us -keep_last_time \
  -s '/tb/clk' '/tb/dut/target' -level 1
vcd2fst -p segment-805-810.vcd segment-805-810.fst
```

Include context before the request and after the response. For transactions crossing a
boundary, overlap windows slightly or extract a window containing the whole transaction.
An initial value at a window start is not necessarily a real transition.

Each export still parses the source FSDB, so excessively small segments add overhead.
Adjust segment length using output size and conversion time. Start sequentially; use limited
concurrency only when server memory, storage, and load permit it.

### Monitor conversion

Check output size, free space, log tails, and your conversion process's PID, elapsed time, and RSS:

```bash
ssh eda01 "du -h '$fsdb_remote_dir'"
ssh eda01 "df -h '$fsdb_remote_dir'"
ssh eda01 "tail -n 20 '$fsdb_remote_dir/focus-800-810.fsdb2vcd.log'"
ssh eda01 'ps -u "$USER" -o pid,etime,pcpu,rss,args'
```

RSS is normally in KiB. VCD growth may reflect declaration or array expansion rather than
progress through simulation time. Wait for both conversion stages to finish; failed or
interrupted conversions may leave incomplete files.

If stopping is necessary, send TERM only to the confirmed PID for your conversion.
Reduce the window, selection, or depth, and retry with a new prefix.

## 7. Access and validate results

### Outputs on shared NFS

For outputs on shared NFS, use the same `fsdb_remote_dir` path locally.
No download is needed:

```bash
(
    cd "$fsdb_remote_dir"
    sha256sum -c focus-800-810.SHA256SUMS
)
```

### Outputs in remote-only scratch space

Copy the completed FST and records. Leave the large intermediate VCD on `eda01`:

```bash
fsdb_prefix=focus-800-810
fsdb_local_export=/absolute/path/to/task/original/analysis/fsdb-export
mkdir -p "$fsdb_local_export"
scp "eda01:$fsdb_remote_dir/$fsdb_prefix.fst" "$fsdb_local_export/"
scp "eda01:$fsdb_remote_dir/$fsdb_prefix.command.txt" \
  "eda01:$fsdb_remote_dir/$fsdb_prefix.summary.txt" \
  "eda01:$fsdb_remote_dir/$fsdb_prefix.fsdb2vcd.log" \
  "eda01:$fsdb_remote_dir/$fsdb_prefix.vcd2fst.log" \
  "eda01:$fsdb_remote_dir/$fsdb_prefix.SHA256SUMS" "$fsdb_local_export/"
(
    cd "$fsdb_local_export"
    sha256sum -c "$fsdb_prefix.SHA256SUMS"
)
```

The FST and checksum file share the same directory, so `sha256sum -c` resolves the recorded relative filename correctly.

Check timescale, export boundaries, and required internal signals. For overlapping exports,
compare representative clock, handshake, address, and state values at identical absolute times.
A successful exit and a nonempty file do not prove that the signal selection is complete.

Retain input identity, tool versions, input/output paths, commands, windows, scope/depth
selections, logs, and checksums so others can reproduce the extraction.

## 8. Common problems

| Symptom | What to check |
| --- | --- |
| `module not found` over SSH | Use a Bash login shell |
| Input missing on eda01 | Check file permissions and whether the input is on shared NFS before copying |
| Slow conversion or growing VCD/memory | Narrow time and scopes, reduce depth, exclude arrays |
| Interfaces present but internal registers missing | Check hierarchy and depth of the target subtree |
| Many apparent transitions at a segment's start | Check whether these are initial states |
| Last signal change precedes export end | Check the final file tag; a signal may stay constant |
| Conversion succeeds but signals are absent | Check selection and whether the source recorded them |
| UVM transactions absent | This VCD/FST path exports RTL signals, not transaction recording |
