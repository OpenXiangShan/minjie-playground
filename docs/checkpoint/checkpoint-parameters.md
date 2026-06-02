# Checkpoint Parameters

The checkpoint scripts provide `generate_checkpoint.py` as the main entry point.

It always runs four stages:
1. `profiling`
2. `cluster`
3. `checkpoint`
4. `metadata`

## Command-Line Parameters

Entry point:
- `scripts/checkpoint/generate_checkpoint.py`

### `--input-path`

- Required
- Can be:
  - A single GCPT bin file
  - A directory containing multiple GCPT bin files
- If a directory is provided, the script scans all regular files under it

### `--name`

- Single-file mode only
- Overrides the automatically derived workload name
- Not allowed in directory mode

### `--archive-id`

- Optional
- Specifies the output archive name
- Required when used with `--resume-after`

Default naming:
- Single-file mode: `<timestamp>_<workload>`
- Directory mode: `<timestamp>_<input-directory>`

### `output_base`

- GitHub Actions input only
- Optional
- Specifies the CI output root
- The default is `/nfs/home/share/<runner-username>/checkpoint-trigger`

### `nemu`

- GitHub Actions input only
- Optional
- The default is `riscv64-xs-cpt_defconfig`
- Values ending with `_defconfig` clone upstream NEMU in the CI workspace and
  build NEMU, `gcpt_restore`, and `simpoint`
- Other values are treated as existing NEMU paths, and the following files must
  exist and be executable:
  - `build/riscv64-nemu-interpreter`
  - `resource/simpoint/simpoint_repo/bin/simpoint`

### `--interval`

- Optional
- The default is `20000000`
- Must be a positive integer
- Passed to both profiling and checkpoint stages

### `--max-k`

- Optional
- Overrides SimPoint `-maxK` during clustering
- Must be a positive integer
- The effective value is `max(built-in workload default, user input)`
- Current built-in special cases:
  - `xalancbmk` has a minimum of `100`
  - Other workloads have a minimum of `30`

### `--max-workers`

- Optional
- The default is `3`
- Only meaningful in directory mode
- Specifies how many workloads can run in parallel

### `--resume-after`

- Optional
- Allowed values:
  - `profiling`
  - `cluster`
  - `auto`

Semantics:
- `profiling`
  Skips profiling and starts from cluster
- `cluster`
  Skips profiling and cluster, then regenerates checkpoints
- `auto`
  Automatically chooses the resume stage based on existing files in the archive

## Automatic Naming

If `--name` is not provided, the script derives the workload name from the file
name.

The currently recognized suffixes are:
- `.fw_payload.bin`
- `.bin`

Examples:
- `gcc_expr.fw_payload.bin` -> `gcc_expr`
- `bwaves.bin` -> `bwaves`

In directory mode, the script first tries to detect the common suffix shared by
all file names, then derives workload names in batch.

## Environment Requirements

Required environment variable:
- `NEMU_HOME`

Required files:
- `$NEMU_HOME/build/riscv64-nemu-interpreter`
- `$NEMU_HOME/resource/simpoint/simpoint_repo/bin/simpoint`

## Output Directories

When the script is run locally, the default output directory is:
- `archive/<archive-id>/`

The GitHub Actions default output directory is:
- `/nfs/home/share/<runner-username>/checkpoint-trigger/<archive-id>/`

When `output_base` is provided to the workflow, outputs are written to:
- `<output_base>/<archive-id>/`

The archive root always contains:
- `profiling/`
- `cluster/`
- `checkpoint/`
- `logs/`
- `metadata/`
- `json/`

The following files are generated during the metadata stage:
- `json/checkpoints_all.json`
- `json/checkpoints_cov0.3.json`
- `checkpoint/checkpoint.lst`
