# Workflow

This document describes the end-to-end FPGA DiffTest flow. Each step lists optional parameters first, then a matching example.

## Common Placeholders

- `<DESIGN>`: top-level design target such as `xiangshan` or `nutshell`
- `<XS_CONFIG>`: XiangShan config used for `make verilog xiangshan`
- `<VIVADO_REMOTE>`: remote machine used for Vivado synthesis and implementation
- `<FPGA_REMOTE>`: remote FPGA host
- `<NEMU_CONFIG>`: NEMU defconfig name
- `<TARGET>`: workload-builder target such as `linux/hello` or `am/hello`
- `<WORKLOAD_TAG>`: workload output directory name, typically `<DESIGN>-$(subst /,-,$(TARGET))`
- `<REMOTE_ROOT>`: remote repository path, typically `/path/to/minjie-playground`
- `<BIT_TAG>`: bitstream bundle directory name under `bitstream/`

## Step 1: Generate Verilog

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `DIFFTEST_CONFIG` | `ESBIFDU` | DiffTest config letters |
| `DIFFTEST_EXCLUDE` | `Vec` | Comma-separated exclude list |
| `JOBS` | `16` | Parallel compilation jobs |
| `XS_CONFIG` | `FpgaDiffDefaultConfig` | XiangShan config used for `xiangshan` builds |

### Example

```sh
export DESIGN=<DESIGN>

make clean $DESIGN
make verilog $DESIGN
```

Output: Verilog files under `<design>/build/`.

For the XiangShan OpenLLC flow, use `XS_CONFIG=FpgaDiffKMHV2Config`.

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

### Example

```sh
make host $DESIGN FPGA_HOST_HOME=$RELEASE_PATH
```

Output: `$RELEASE_PATH/build/fpga-host`

## Step 4: Generate Bitstream

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `REMOTE` | empty | Remote host for Vivado execution |
| `REMOTE_DIR` | repository root | Repository path on the remote host |
| `REMOTE_ENV` | `source ~/.bash_profile &&` | Remote environment setup command |
| `BIT_SRC_DIR` | latest release | Release directory used for synthesis |
| `SUFFIX` | empty | Suffix appended to the Vivado project directory name |
| `BIT_TAG` | `<design>-<timestamp>` | Bitstream bundle directory name under `bitstream/` |
| `CHI_DIR` | empty | Extra CHI glue RTL/header directory for external NoC CHI wrappers |

### Example

```sh
make bit \
  $DESIGN \
  REMOTE=<VIVADO_REMOTE> \
  REMOTE_DIR=/path/to/minjie-playground

export BIT_TAG=<BIT_TAG>
```

Output:

```text
bitstream/$BIT_TAG/
bitstream/$BIT_TAG/$RELEASE_NAME/
bitstream/$BIT_TAG/*.bit
bitstream/$BIT_TAG/*.ltx
```

Set `CHI_DIR` only for flows that use an external CHI-interface NoC. The
OpenLLC flow does not need `CHI_DIR`.

## Step 5: Build NEMU Reference

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `NEMU_CONFIG` | `riscv64-xs-ref-novec-nopmppma_defconfig` | NEMU defconfig used to build the reference SO |

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
| `WORKLOAD_DTB` | `xiangshan-fpga-noAIA.dtb` | Linux DTB used before Bin2ddr |
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
| `FPGA_BIT_HOME` | none | Bitstream bundle directory |
| `WORKLOAD` | none | Workload directory containing `.bin` and `.txt` |
| `DIFF` | empty | NEMU SO path for diff mode |
| `HOST` | $FPGA_BIT_HOME/*/build/fpga-host | Explicit `fpga-host` path override |

Before using the shared VU19P board, initialize and inspect the occupancy marker:

```sh
make fpga_init REMOTE=<FPGA_REMOTE> REMOTE_DIR=$REMOTE_ROOT
make fpga_status REMOTE=<FPGA_REMOTE> REMOTE_DIR=$REMOTE_ROOT
```

The marker lives under `~/.fpga_used/` on the FPGA host. The default board files are:

```text
~/.fpga_used/vu19p.status
~/.fpga_used/vu19p.in_use
~/.fpga_used/vu19p.idle
```

### Example

```sh
export BIT_ROOT=$REMOTE_ROOT/bitstream/$BIT_TAG

make write_bitstream \
  REMOTE=<FPGA_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT

make run_host \
  REMOTE=<FPGA_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$REMOTE_ROOT/ready-to-run/$WORKLOAD_TAG \
  DIFF=$REMOTE_ROOT/ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so
```

`run_host` auto-finds `fpga-host` under `FPGA_BIT_HOME`, picks the `.bin` and `.txt` inside `WORKLOAD`, auto-generates `FPGA_DDR_LOAD_CMD`, and releases the occupancy marker automatically when `fpga-host` exits.

### Manual Debug Path

If you want to separate DDR load from `fpga-host`, use:

```sh
make write_jtag_ddr \
  REMOTE=<FPGA_REMOTE> \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$REMOTE_ROOT/ready-to-run/$WORKLOAD_TAG
```

For manual reservation or cleanup:

```sh
make fpga_claim REMOTE=<FPGA_REMOTE> REMOTE_DIR=$REMOTE_ROOT
make fpga_release REMOTE=<FPGA_REMOTE> REMOTE_DIR=$REMOTE_ROOT
```

`write_bitstream`, `write_jtag_ddr`, `reset_cpu`, and `run_host` all check the occupancy marker before touching the board. If you stop after a manual flash / DDR / reset sequence without calling `run_host`, release the board explicitly with `make fpga_release`.

## Next Steps

- For repository structure, see [layout.md](./layout.md).
- For workload customization, see [workload.md](./workload.md).
- If something fails, see [troubleshooting.md](./troubleshooting.md).
- For longer investigations, see [debug-flow.md](./debug-flow.md).
