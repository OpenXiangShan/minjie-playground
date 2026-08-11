# Checkpoint Scripts

This directory generates checkpoints from GCPT-bootable bin files, including
workload-builder virtualized Host/QEMU/KVM/Guest payloads.

Inputs can be:
- A single bin file
- A directory containing multiple bin files

In multi-bin mode, all workloads are collected into one archive. The default
stage directories are:
- `profiling`
- `cluster`
- `checkpoint`
- `logs`
- `metadata`
- `json`

## Flow Stages

The scripts under `scripts/checkpoint/` are organized by stage:

- `generate_checkpoint.py`
  Main entry point. It detects the input type, dispatches workloads, handles
  resume mode, and aggregates metadata.
- `step_profiling.py`
  Generates BBV files.
- `step_cluster.py`
  Runs SimPoint clustering.
- `step_checkpoint.py`
  Generates checkpoints from cluster points and validates the outputs.
- `step_metadata.py`
  Generates `json/*.json` and `checkpoint/checkpoint.lst`.
  The main entry point also manages archive/stage paths and validates
  `NEMU_HOME` and runtime tools.

## GitHub Action

Use the repository `Checkpoint` workflow for CI runs.

Common inputs:
- `input_path`
  Required. It can be a single bin file or a directory.
- `name`
  Single-file mode only. Overrides the workload name.
- `archive_id`
  Optional. Specifies the output directory name, or points to an existing
  archive when resuming.
- `output_base`
  GitHub Actions only. Specifies the CI output root. The default is
  `/nfs/home/share/<runner-username>/checkpoint-trigger`.
- `interval`
  Checkpoint interval. The default is `20000000`.
- `max_k`
  Optional. Overrides SimPoint `-maxK`. The effective value is
  `max(built-in workload default, user input)`.
- `max_workers`
  Maximum number of parallel workloads in directory mode. The default is `3`.
- `nemu`
  Optional. The default is `riscv64-xs-cpt_defconfig`.
  Values ending with `_defconfig` clone and build upstream NEMU in the CI
  workspace. Other values are treated as existing NEMU paths and are validated
  before use.
- `resume_after`
  Optional. Supported values are `profiling`, `cluster`, and `auto`.

See [checkpoint-parameters.md](./checkpoint-parameters.md) for full parameter
semantics and environment requirements.

The GitHub Actions workflow currently runs native single-core checkpoints only.
Multi-hart runs using `--copies > 1` are supported through local usage.
Virtualized ROI runs using `--virtualized` are also local-only.

The workflow timeout is currently 28 days.

## Local Usage

Prepare a built NEMU and set `NEMU_HOME`:

```bash
export NEMU_HOME=/path/to/NEMU
```

Required environment and tools:
- `NEMU_HOME` is set
- `$NEMU_HOME/build/riscv64-nemu-interpreter` exists
- `$NEMU_HOME/resource/simpoint/simpoint_repo/bin/simpoint` exists

When `--copies` is greater than `1`, profiling and checkpoint generation run
with QEMU. Set `QEMU_HOME` and make sure these files exist:

- `$QEMU_HOME/build/qemu-system-riscv64`
- `$QEMU_HOME/build/contrib/plugins/libprofilingv2.so`

Single bin:

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/demo.fw_payload.bin \
  --name demo \
  --archive-id demo-checkpoint
```

Multiple bins:

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/bin-directory \
  --interval 20000000 \
  --copies 32 \
  --qemu-memory 64G \
  --max-k 40 \
  --max-workers 3
```

Multi-hart checkpoint from an existing GCPT bin:

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/multihart.gcpt.bin \
  --name demo \
  --copies 2 \
  --archive-id demo-multihart-checkpoint
```

`--copies` records the hart count encoded in the GCPT bin. Values above `1`
automatically use QEMU for profiling and checkpoint generation with
`-smp <copies>`. The value must match the enabled CPU count in the embedded
workload DTB; a mismatch is rejected before a runtime stage starts.

When `--qemu-memory` is omitted, the script derives QEMU's `-m` value from the
workload DTB. Pass `--qemu-memory` to override the detected value.

### Virtualized workload

Virtualized payloads are built separately by workload-builder with targets such
as `make virt/linux/spec2006`. The resulting `host/fw_payload.bin` already
contains the LibCheckpointAlpha-virt restorer and is consumed directly; this
repository does not rebuild or modify the payload.

Use a NEMU built with UART marker-gated profiling and enough memory for the
payload's Host DTB. The validated reference is commit `4c9099dc`, configured with 16 GiB.

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /nfs/home/wujiabin/work/workload-builder/build/virt-linux-workloads/astar_biglakes/host/fw_payload.bin \
  --name astar_biglakes \
  --virtualized \
  --archive-id astar-biglakes-virtual-checkpoint
```

Virtual mode profiles the complete ROI between the default UART markers
`exec command:` and `TEST DONE!`. `--virtual-max-instr` optionally places a
hard limit on total outer-NEMU instructions; without it, the stop marker ends
profiling naturally. An instruction-limit exit before the stop marker is an
error and the partial BBV is rejected.

The checkpoint stage reads the observed profiling marker base and runs through
`marker_base + (max_simpoint + 2) * interval`. It therefore does not need to
rerun the complete workload after clustering. Custom workload wrappers may use
`--virtual-start-marker` and `--virtual-stop-marker`.

Virtual mode requirements and restrictions:

- The outer Host payload must contain exactly one enabled hart.
- `--copies` must remain `1`; nested Guest vCPUs are internal to the payload.
- `--qemu-memory` is not accepted because profiling still runs in outer NEMU.
- `--name` is required for a single file.
- `NEMU_HOME/.config` must have `CONFIG_MSIZE` at least as large as the embedded
  Host DTB memory and the NEMU `--help` output must expose both UART marker
  options.

Resume:

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/bin-directory \
  --archive-id 2026-05-17-12-00-00_bin-directory \
  --resume-after auto
```

For virtual mode, resume from `profiling`, `cluster`, or `auto` additionally
requires the original profiling logs. The logs provide the marker base, full
ROI instruction count, and proof that the stop marker was reached. Missing or
incomplete marker evidence is rejected.

## Naming Rules

- In single-file mode, when `--name` is not provided, the workload name is
  derived from the file name by removing known suffixes.
- In directory mode, workload names are derived by detecting the common suffix
  shared by all file names.
- The default archive name in single-file mode is `<timestamp>_<workload>`.
- The default archive name in directory mode is `<timestamp>_<input-directory>`.
- The main built-in suffixes are `.fw_payload.bin` and `.bin`.

Examples:
- `gcc_166.fw_payload.bin` -> `gcc_166`
- `astar_biglakes.bin` -> `astar_biglakes`

## Output Layout

When `generate_checkpoint.py` is run locally, the default output root is the
repository-local `archive/` directory.

The GitHub Actions default output root is
`/nfs/home/share/<runner-username>/checkpoint-trigger/`.

When `output_base` is provided to the workflow, outputs are written under that
directory instead.

Example archive:

```text
/nfs/home/share/alice/checkpoint-trigger/2026-05-17-12-00-00_spec-bins/
├── checkpoint/
├── cluster/
├── json/
├── logs/
├── metadata/
└── profiling/
```

Directory contents:
- `metadata/`
  Stores the batch request and per-workload request records.
- `json/`
  Stores per-workload JSON files and:
  - `checkpoints_all.json`
  - `checkpoints_cov0.3.json`
- `checkpoint/checkpoint.lst`
  Aggregated checkpoint list.

## GCPT Patch

If checkpoint generation gets stuck immediately, the GCPT input is likely
invalid and a correct `gcpt.bin` should be generated again.

For a virtualized workload, check the profiling logs for these messages:

```text
ROI uart marker matched: exec command:
Start profiling. Setting inst count base to Current inst count ...
ROI uart stop marker matched: TEST DONE!
ROI dynamic instructions = ...
```

If the first marker is absent, verify that the workload-builder Host forwards
Guest serial output and that `--virtual-max-instr` is large enough to reach the
Guest. If the stop marker is absent, the Guest workload failed, hung, or hit the
hard instruction limit; the generated BBV is intentionally not accepted.

`scripts/checkpoint/replace_checkpoint_prefix.py` replaces the GCPT prefix in
existing checkpoint files in batches. It recursively processes `*.gz` and
`*.zstd` files under a checkpoint directory, detects gzip or Zstandard from
the file contents rather than the suffix, replaces the beginning of each
decompressed payload with the specified `gcpt.bin`, recompresses the result
into a new output directory, and preserves relative paths.

Requirements:
- The `zstd` command must be available in `PATH` when any input is
  Zstandard-compressed. Gzip inputs use Python's standard library.
- `--gcpt-bin` points to the new `gcpt.bin`.
- `--checkpoint-dir` points to the generated checkpoint directory.
- `--output-dir` points to the new output directory. It must not be the same as
  the source directory or be located inside the source directory.

Example:

```bash
python3 scripts/checkpoint/replace_checkpoint_prefix.py \
  --gcpt-bin /path/to/gcpt.bin \
  --checkpoint-dir /path/to/archive/checkpoint \
  --output-dir /path/to/archive/checkpoint-gcpt-patched
```

This script only rewrites compressed checkpoint file contents. It does not
update `json/`, `metadata/`, or `checkpoint/checkpoint.lst`.
