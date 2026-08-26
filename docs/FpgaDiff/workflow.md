# Workflow

This document describes the end-to-end FPGA DiffTest flow. Each step lists optional parameters first, then a matching example.

## Common Placeholders

- `<DESIGN>`: top-level design target such as `xiangshan` or `nutshell`
- `<XS_CONFIG>`: XiangShan config used for `make verilog xiangshan`
- `<FPGA_BUILD_REMOTE>`: remote machine used by the selected FPGA backend
- `<FPGA_REMOTE>`: remote FPGA host
- `<FPGA_RUNTIME_REMOTE>`: FPGA host for Vivado, or the UVHS runtime host for UVHS
- `<CPU>`: backend CPU name, such as `kmh` or `nutshell`
- `<NEMU_CONFIG>`: NEMU defconfig name
- `<TARGET>`: workload-builder target such as `linux/hello` or `am/hello`
- `<WORKLOAD_TAG>`: workload output directory name, typically `<DESIGN>-$(subst /,-,$(TARGET))`
- `<REMOTE_ROOT>`: remote repository path, typically `/path/to/minjie-playground`
- `<BIT_TAG>`: bitstream bundle directory name under `bitstream/`
- `<BOOTRAM_BIN>`: raw boot image to stage in the JTAG boot flash
- `<FPGA_BACKEND>`: FPGA implementation/runtime backend, `vivado` or `uvhs`

## Step 1: Generate Verilog

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `DIFFTEST_CONFIG` | `ESBIFDU` | DiffTest config letters |
| `DIFFTEST_EXCLUDE` | empty | Comma-separated exclude list, such as `Vec` |
| `JOBS` | `16` | Parallel compilation jobs |
| `XS_CONFIG` | `FpgaDiffDefaultConfig` | XiangShan config used for `xiangshan` builds |

### Example

```sh
export DESIGN=<DESIGN>

make clean $DESIGN
make verilog $DESIGN
```

Output: Verilog files under `<design>/build/`.

For the XiangShan external-LLC flow, select the matching configuration and pass
the generator flag explicitly:

```sh
make verilog xiangshan \
  XS_CONFIG=FpgaDiffKMHV2Config \
  XS_DEBUG_ARGS="--difftest-config ESBIFDU --external-llc"
```

For a no-vector XiangShan build, explicitly pass `DIFFTEST_EXCLUDE=Vec`.

## Step 2: Create Release

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `RELEASE_SUFFIX` | current `HHMMSS` | Suffix appended to the release name |

### Example

```sh
make release $DESIGN

export RELEASE_PATH=$(cat build/release/latest-$DESIGN.path)
export RELEASE_NAME=$(cat build/release/latest-$DESIGN.name)
```

Output:

```text
build/release/$RELEASE_NAME/
build/release/latest-$DESIGN.path
build/release/latest-$DESIGN.name
```

## Step 3: Build FPGA Host

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `FPGA_HOST_HOME` | none | Release directory used to build `fpga-host` |
| `FPGA_HOST_ARGS` | `RELEASE=1 FPGA=1 DIFFTEST_PERFCNT=1` | Additional host build arguments |
| `USE_XDMA_H2C` | `1` | Build `fpga-host` with XDMA H2C workload loading. Set to `0` for the external DDR load hook |

### Example

```sh
make host $DESIGN FPGA_HOST_HOME=$RELEASE_PATH
```

Output: `$RELEASE_PATH/build/fpga-host`

The default host build enables `CONFIG_USE_XDMA_H2C`, so `fpga-host` writes the workload image to DDR through `/dev/xdma0_h2c_0`. This H2C path does not program the FPGA boot flash.
The external DDR loader is still available by rebuilding the host with `USE_XDMA_H2C=0`.

## Step 4: Generate Bitstream

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `REMOTE` | empty | Remote host for the selected FPGA backend |
| `REMOTE_DIR` | repository root | Repository path on the remote host |
| `REMOTE_ENV` | `source ~/.bash_profile &&` | Remote environment setup command |
| `FPGA_BACKEND` | `vivado` | Select `vivado` or `uvhs` for FPGA build and runtime commands |
| `PRJ_NAME` | `fpga_<backend>_<cpu>[-<suffix>]` | Stable project/work-directory name used by build and runtime targets |
| `BIT_SRC_DIR` | latest release | Release directory used for synthesis |
| `SUFFIX` | empty | Suffix used by the default project name |
| `BIT_TAG` | `<design>-<timestamp>` | Bitstream bundle directory name under `bitstream/` |
| `RTL_INCLUDE` | empty | Extra RTL file, directory, or file list forwarded to `env-scripts/fpga_diff` |

### Example

```sh
make bit \
  $DESIGN \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_BUILD_REMOTE> \
  REMOTE_DIR=/path/to/minjie-playground

export BIT_TAG=<BIT_TAG>
```

With `FPGA_BACKEND=vivado`, output is:

```text
bitstream/$BIT_TAG/
bitstream/$BIT_TAG/$RELEASE_NAME/
bitstream/$BIT_TAG/*.bit
bitstream/$BIT_TAG/*.ltx
```

`env-scripts/fpga_diff` defaults `DDR_RANK_WIDTH=2`, selecting the 16GB two-rank DDR configuration:
a 34-bit DDR AXI address, the `MTA16ATF2G64HZ-2G3` memory part, and `ddr_rank1.xdc`.
This physical DDR configuration is independent of the `RAM_SIZE` passed to `fpga-host` below.

With `FPGA_BACKEND=uvhs`, the same `bit` target forwards the release and
`RTL_INCLUDE` inputs to the UVHS frontend/backend flow. The remote shell must
already provide the vendor tool, license, template, and IP environment required
by `env-scripts/fpga_diff`; those site-specific settings are intentionally not
stored in this repository.

Playground uses the backend-neutral `project` and `bitstream` targets in
`env-scripts/fpga_diff`. `make project` prepares the selected backend without
running the complete bitstream flow.

### XiangShan External LLC

The external-LLC RTL file list must accompany the RTL generated with
`--external-llc`. Pass it through the top-level build for either backend:

```sh
make bit xiangshan \
  FPGA_BACKEND=<FPGA_BACKEND> \
  RTL_INCLUDE=/path/to/external_llc.f \
  REMOTE=<FPGA_BUILD_REMOTE> \
  REMOTE_DIR=/path/to/minjie-playground
```

The `RTL_INCLUDE` path must be visible on the build host. For a project-only
run, pass the same file list explicitly:

```sh
make project FPGA_BACKEND=<FPGA_BACKEND> \
  CPU=kmh CORE_DIR="$RELEASE_PATH/build" \
  RTL_INCLUDE=/path/to/external_llc.f
```

## Step 5: Build NEMU Reference

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `NEMU_CONFIG` | `riscv64-xs-ref_defconfig` | NEMU defconfig used to build the reference SO |

### Example

```sh
export NEMU_CONFIG=<NEMU_CONFIG>
make nemu NEMU_CONFIG=$NEMU_CONFIG
```

Output: `ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so`

## Step 6: Build Workload

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `TARGET` | `linux/hello` | Workload-builder target |
| `WORKLOAD_DTB` | `xiangshan-fpga-AIA-mem16g.dtb` | Linux DTS selection and DTB used before Bin2ddr |
| `AM_ARCH` | inferred from `DESIGN` | AM ISA/platform selection |

### Example

```sh
export TARGET=<TARGET>
export WORKLOAD_TAG=<WORKLOAD_TAG>

make workload $DESIGN TARGET=$TARGET
```

Output:

```text
ready-to-run/$WORKLOAD_TAG/$WORKLOAD_TAG.bin
ready-to-run/$WORKLOAD_TAG/$WORKLOAD_TAG.txt
```

AM and Linux workload details are described separately in [workload.md](./workload.md).

## Step 7: Sync to FPGA Host

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `<FPGA_REMOTE>` | none | Remote FPGA host |
| `<REMOTE_ROOT>` | `/path/to/minjie-playground` | Repository path on the FPGA host |

### Example

```sh
export REMOTE_ROOT=/path/to/minjie-playground

ssh <FPGA_REMOTE> "mkdir -p $REMOTE_ROOT/bitstream $REMOTE_ROOT/ready-to-run"
rsync -a --delete bitstream/$BIT_TAG/ <FPGA_REMOTE>:$REMOTE_ROOT/bitstream/$BIT_TAG/
rsync -a --delete ready-to-run/ <FPGA_REMOTE>:$REMOTE_ROOT/ready-to-run/
```

## Step 8: Write Bitstream and Run

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `REMOTE` | empty | Remote execution target |
| `REMOTE_DIR` | repository root | Repository path on the remote target |
| `FPGA_BACKEND` | `vivado` | Use the same backend selected for `make bit` |
| `FPGA_BIT_HOME` | none | Bitstream bundle directory |
| `WORKLOAD` | none | Workload directory containing `.bin` and `.txt` |
| `DIFF` | empty | NEMU SO path for diff mode |
| `HOST` | $FPGA_BIT_HOME/*/build/fpga-host | Explicit `fpga-host` path override |
| `RAM_SIZE` | `16GB` for XiangShan; `2GB` for NutShell | Forwarded as `--ram-size=$(RAM_SIZE)` |
| `RANDOM_MEM` | `1` | Set to `1` to pass `--random-mem --seed=$(SEED)` |
| `SEED` | `1234` | Random DDR initialization seed when `RANDOM_MEM=1` |
| `RUN_HOST_ARGS` | derived from `DIFF`, `WORKLOAD`, `RAM_SIZE`, `RANDOM_MEM`, `SEED` | Full argument list passed to `fpga-host` |

### Example

```sh
export BIT_ROOT=$REMOTE_ROOT/bitstream/$BIT_TAG

make write_bitstream \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT

make run_host \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$REMOTE_ROOT/ready-to-run/$WORKLOAD_TAG \
  DIFF=$REMOTE_ROOT/ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so
```

An external-LLC image also requires its boot ROM in the writable boot flash.
After `write_bitstream`, write `<BOOTRAM_BIN>` before releasing the CPU. The
top-level target selects the Vivado or UVHS implementation:

```sh
make write_flash \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_RUNTIME_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=<BOOTRAM_BIN>
```

`run_host` auto-finds `fpga-host` under `FPGA_BIT_HOME` and picks the `.bin` and `.txt` inside `WORKLOAD`.

`FPGA_BACKEND` also selects the implementation of `write_bitstream`,
`write_ddr`, `write_flash`, and `reset_cpu`. The default `vivado`
backend preserves the existing Vivado/JTAG behavior. With `FPGA_BACKEND=uvhs`,
the same runtime-control targets operate on the active UVHS database and do not
require `FPGA_BIT_HOME`. `run_host` still uses `FPGA_BIT_HOME` to locate the
release containing `fpga-host`.

For UVHS, `write_bitstream` downloads the implementation database and starts a
persistent runtime session. Check or stop that session from its env-scripts
checkout:

```sh
make -C env-scripts/fpga_diff runtime_status \
  FPGA_BACKEND=uvhs CPU=<CPU> SUFFIX=<tag>

make -C env-scripts/fpga_diff runtime_stop \
  FPGA_BACKEND=uvhs CPU=<CPU> SUFFIX=<tag>
```

When `FPGA_BACKEND=uvhs`, `run_host` automatically sets `FPGA_ILA_ARM_CMD` and
`FPGA_ILA_UPLOAD_CMD`. In a two-host setup, run `fpga-host` on the FPGA host and
point the hooks at the machine that owns the UVHS runtime:

```sh
make run_host \
  FPGA_BACKEND=uvhs \
  REMOTE=<FPGA_HOST_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=<HOST_RELEASE_DIR> \
  WORKLOAD=<WORKLOAD_DIR> \
  DIFF=<NEMU_SO> \
  CPU=<CPU> SUFFIX=<tag>
```

The generated commands source the runtime user's shell environment before
calling the backend-neutral `env-scripts` ILA arm/upload targets. Backend
dispatch and command construction stay inside `env-scripts`; playground only
passes `FPGA_BACKEND` and `UVHS_RUNTIME`.

The UVHS upload creates `UvData.usdb` and `UvData.vcd` under
`env-scripts/fpga_diff/<PRJ_NAME>/runtime-work/UHD/uvhs_ila/` on the UVHS
runtime host. The current hook prints those remote paths but does not copy the
files back to the FPGA host or the machine that invoked `make run_host`.

With `USE_XDMA_H2C=1` (the default), the host writes only the workload `.bin` to DDR through XDMA H2C before releasing the CPU. It does not write the FPGA boot flash.

With `USE_XDMA_H2C=0`, the host writes DDR with external `FPGA_DDR_LOAD_CMD`:

```sh
make write_ddr \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_RUNTIME_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$REMOTE_ROOT/ready-to-run/$WORKLOAD_TAG/$WORKLOAD_TAG.txt
```

### DDR Fallback / Debug Path

The direct `write_ddr` target is available for manual debugging and host builds
made with `USE_XDMA_H2C=0`; normal `run_host` uses H2C for DDR loading.

### Boot Flash Path

For designs that require a boot image in flash, write it after every
`write_bitstream`.

```sh
make write_flash \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_RUNTIME_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=<BOOTRAM_BIN>
```

## Next Steps

- For repository structure, see [layout.md](./layout.md).
- For workload customization, see [workload.md](./workload.md).
- If something fails, see [troubleshooting.md](./troubleshooting.md).
- For longer investigations, see [debug-flow.md](./debug-flow.md).
