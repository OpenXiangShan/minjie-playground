# Workflow

This document describes the end-to-end FPGA DiffTest flow. Each step lists optional parameters first, then a matching example.

## Common Placeholders And Hosts

- `<DESIGN>`: top-level design target such as `xiangshan` or `nutshell`
- `<XS_CONFIG>`: XiangShan config used for `make verilog xiangshan`
- `<FPGA_BUILD_REMOTE>`: remote machine used by the selected FPGA backend
- `$FPGA_HOST`: host that owns XDMA and runs `fpga-host`; empty means local
- `$FPGA_RUNTIME`: programming/runtime host; defaults to `$FPGA_HOST`
- `$FPGA_HOST_DIR`: absolute Minjie checkout path on `$FPGA_HOST`
- `$FPGA_RUNTIME_DIR`: absolute Minjie checkout path on `$FPGA_RUNTIME`
- `$FPGA_RUNTIME_HOME`: absolute copied UVHS project path containing `hw.dat`
- `<CPU>`: backend CPU name, such as `kmh` or `nutshell`
- `<NEMU_CONFIG>`: NEMU defconfig name
- `<TARGET>`: workload-builder target such as `linux/hello` or `am/hello`
- `<WORKLOAD_TAG>`: workload output directory name, typically `<DESIGN>-$(subst /,-,$(TARGET))`
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

The target also prints `FPGA_HOST_HOME` and `FPGA_HOST_BINARY` with absolute
paths so the completed release can be copied without rediscovering it.

The default host build enables `CONFIG_USE_XDMA_H2C`, so `fpga-host` writes the workload image to DDR through `/dev/xdma0_h2c_0`. This H2C path does not program the FPGA boot flash.
The external DDR loader is still available by rebuilding the host with `USE_XDMA_H2C=0`.

## Step 4: Generate Bitstream

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `REMOTE` | empty | Optional NFS-sharing FPGA build host |
| `REMOTE_ENV` | `source ~/.bashrc &&` | Build-host environment setup command |
| `FPGA_BACKEND` | `vivado` | Select `vivado` or `uvhs` for FPGA build and runtime commands |
| `BIT_SRC_DIR` | latest release | Release directory used for synthesis |
| `SUFFIX` | empty | Suffix used by the default project name |
| `BIT_TAG` | `<design>-<timestamp>` | Bitstream bundle directory name under `bitstream/` |
| `RTL_INCLUDE` | empty | Extra RTL file, directory, or file list forwarded to `env-scripts/fpga_diff` |

### Example

```sh
make bit \
  $DESIGN \
  FPGA_BACKEND=<FPGA_BACKEND> \
  REMOTE=<FPGA_BUILD_REMOTE>

export BIT_TAG=<BIT_TAG>
```

`REMOTE` is optional. When set, the build host enters the same absolute checkout
path visible through NFS and sources `~/.bashrc`. `PRJ_NAME` is always derived as
`fpga_<backend>_<cpu>[-<suffix>]`.

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
  REMOTE=<FPGA_BUILD_REMOTE>
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

## Step 7: Sync to FPGA Machines

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `FPGA_HOST` | none | Host receiving release and workload artifacts |
| `FPGA_RUNTIME` | `$FPGA_HOST` | Runtime receiving UVHS database and boot image when paths are not shared |
| `FPGA_HOST_DIR` | current checkout | Absolute Minjie checkout path on the FPGA host |
| `FPGA_RUNTIME_DIR` | `$FPGA_HOST_DIR` | Absolute Minjie checkout path on the runtime host |

### Example

```sh
export FPGA_HOST_DIR=/path/to/minjie-playground
export FPGA_RUNTIME_DIR=/path/to/minjie-playground

ssh "$FPGA_HOST" "mkdir -p $FPGA_HOST_DIR/bitstream $FPGA_HOST_DIR/ready-to-run"
rsync -a --delete bitstream/$BIT_TAG/ \
  "$FPGA_HOST:$FPGA_HOST_DIR/bitstream/$BIT_TAG/"
rsync -a --delete ready-to-run/ "$FPGA_HOST:$FPGA_HOST_DIR/ready-to-run/"
```

`make bit` prints `FPGA_BIT_HOME`, while the UVHS backend additionally prints
`FPGA_RUNTIME_HOME`. Copy the former to `$FPGA_HOST`; copy the latter to
`$FPGA_RUNTIME` when its storage is not shared with the build machine. The
runtime path supplied as `FPGA_RUNTIME_HOME` is then enough for env-scripts to
find `hw.dat` and its runtime state. External-LLC flows must also place
`<BOOTRAM_BIN>` on the runtime before `write_flash`.

```sh
# The printed source is the clean runtime/ directory inside the bit archive.
export BUILD_FPGA_RUNTIME_HOME=<printed-FPGA_RUNTIME_HOME>
rsync -a "$BUILD_FPGA_RUNTIME_HOME/" \
  "$FPGA_RUNTIME:$FPGA_RUNTIME_DIR/runtime-artifacts/fpga_uvhs_<cpu>-<tag>/"
FPGA_RUNTIME_HOME=$FPGA_RUNTIME_DIR/runtime-artifacts/fpga_uvhs_<cpu>-<tag>
rsync -a "$BOOTRAM_BIN" "$FPGA_RUNTIME:$FPGA_RUNTIME_DIR/ready-to-run/bootram.bin"
```

## Step 8: Write Bitstream and Run

### Optional Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `FPGA_BACKEND` | `vivado` | Use the same backend selected for `make bit` |
| `FPGA_HOST` | local | XDMA and `fpga-host` machine; empty means local |
| `FPGA_RUNTIME` | `$FPGA_HOST` | Bitstream, reset, memory, and ILA machine; empty means local |
| `FPGA_HOST_DIR` | current checkout | Absolute Minjie checkout path on `FPGA_HOST` |
| `FPGA_RUNTIME_DIR` | `$FPGA_HOST_DIR` | Absolute Minjie checkout path on `FPGA_RUNTIME` |
| `FPGA_RUN_ENV` | `source ~/.bash_profile &&` | Environment setup for host/runtime commands |
| `FPGA_RUNTIME_HOME` | empty | Absolute runtime-side UVHS project or Vivado bit path override |
| `UVHS_ILA_GATED_CLOCK` | `inter_soc_clk` for KMH/XiangShan | Comma-separated gated capture clocks |
| `FPGA_KEEP_RUNTIME` | `0` | Set to `1` to retain UVHS for consecutive `run_host` invocations |
| `FPGA_BIT_HOME` | none | Bitstream bundle directory |
| `WORKLOAD` | none | Workload directory containing `.bin` and `.txt` |
| `DIFF` | empty | NEMU SO path for diff mode |
| `HOST` | $FPGA_BIT_HOME/*/build/fpga-host | Explicit `fpga-host` path override |
| `RAM_SIZE` | `16GB` for XiangShan; `2GB` for NutShell | Forwarded as `--ram-size=$(RAM_SIZE)` |
| `RANDOM_MEM` | `1` | Set to `1` to pass `--random-mem --seed=$(SEED)` |
| `SEED` | `1234` | Random DDR initialization seed when `RANDOM_MEM=1` |
| `RUN_HOST_ARGS` | derived from `DIFF`, `WORKLOAD`, `RAM_SIZE`, `RANDOM_MEM`, `SEED` | Full argument list passed to `fpga-host` |

For an FPGA machine without the build machine's NFS mount, set its checkout
directory explicitly with `FPGA_HOST_DIR` or `FPGA_RUNTIME_DIR`.

### Vivado Example

```sh
export BIT_ROOT=$FPGA_HOST_DIR/bitstream/$BIT_TAG

make write_bitstream \
  FPGA_BACKEND=vivado \
  FPGA_HOST=$FPGA_HOST \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_BIT_HOME=$BIT_ROOT

make run_host \
  FPGA_BACKEND=vivado \
  FPGA_HOST=$FPGA_HOST \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$FPGA_HOST_DIR/ready-to-run/$WORKLOAD_TAG \
  DIFF=$FPGA_HOST_DIR/ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so
```

An external-LLC Vivado image also requires its boot ROM in the writable boot
flash. After every `write_bitstream`, write `<BOOTRAM_BIN>` before `run_host`:

```sh
make write_flash \
  FPGA_BACKEND=vivado \
  FPGA_HOST=$FPGA_HOST \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=<BOOTRAM_BIN>
```

`run_host` auto-finds `fpga-host` under `FPGA_BIT_HOME` and picks the `.bin` and `.txt` inside `WORKLOAD`.

An empty `FPGA_HOST` means the current machine. `FPGA_RUNTIME` defaults to
`FPGA_HOST`, which is the normal Vivado topology. Set them separately for UVHS.
`FPGA_BACKEND` also selects the implementation of `write_bitstream`,
`write_ddr`, `write_flash`, and `reset_cpu`. The default `vivado`
backend preserves the existing Vivado/JTAG behavior. With `FPGA_BACKEND=uvhs`,
the same runtime-control targets operate on the active UVHS database and do not
require `FPGA_BIT_HOME`. `run_host` still uses `FPGA_BIT_HOME` to locate the
release containing `fpga-host`.

### UVHS Runtime And Host

The UVHS flow uses two machines. `$FPGA_RUNTIME` owns the UVHS database, reset,
flash, DDR backdoor, physical UART, and ILA. `$FPGA_HOST` owns the Linux PCIe
endpoint, XDMA driver and device nodes, and `fpga-host`.

When `$FPGA_RUNTIME` and `$FPGA_HOST` differ, Minjie removes the `10ee:9048`
endpoint on `$FPGA_HOST`, invokes the original env-scripts `write_bitstream` on
`$FPGA_RUNTIME`, then rescans `$FPGA_HOST`. An exit trap also attempts the
rescan when programming fails. When both variables name the same machine, the
backend keeps its original local behavior; Vivado performs its own remove and
rescan. The remove step refuses to continue while `fpga-host` is running. The
rescan prints the live PCI configuration value, driver, nodes, and permissions.

```sh
make write_bitstream \
  FPGA_BACKEND=uvhs \
  FPGA_HOST=$FPGA_HOST \
  FPGA_RUNTIME=$FPGA_RUNTIME \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_RUNTIME_DIR=$FPGA_RUNTIME_DIR \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME \
  CPU=<CPU> SUFFIX=<tag>
```

UVHS restores the CPU clock to the sign-off frequency stored in `hw.dat`. It
does not use a separate workload-loading frequency. The UART clock remains
50 MHz, and TMCLK is derived from the configured CPU-to-TMCLK ratio.

After an external-LLC runtime download, write the boot image on the runtime
host before starting `fpga-host`:

```sh
make write_flash \
  FPGA_BACKEND=uvhs \
  FPGA_HOST=$FPGA_HOST \
  FPGA_RUNTIME=$FPGA_RUNTIME \
  FPGA_RUNTIME_DIR=$FPGA_RUNTIME_DIR \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME \
  CPU=<CPU> SUFFIX=<tag> \
  WORKLOAD=$FPGA_RUNTIME_DIR/ready-to-run/bootram.bin
```

The UVHS flash command performs a complete readback internally. A separate
manual readback is needed only when diagnosing a write or boot failure.

When the physical UART is attached to the runtime host, create the bridge from
the FPGA host. The target maps the remote UART to `/tmp/fpga-remote-uart`,
exports `FPGA_UART_PORT`, and opens the shell used to run `fpga-host`:

```sh
make bind_uart \
  FPGA_HOST=$FPGA_HOST \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_RUNTIME=<user@fpga-runtime> \
  REMOTE_UART_PORT=/dev/serial/by-id/<uart-device>
```

Replace <user@fpga-runtime> with an SSH target resolvable from $FPGA_HOST; it
may be a configured alias or a user@hostname destination.

The normal host invocation points ILA commands back to the runtime host:

```sh
make run_host \
  FPGA_BACKEND=uvhs \
  FPGA_HOST=$FPGA_HOST \
  FPGA_RUNTIME=$FPGA_RUNTIME \
  FPGA_HOST_DIR=$FPGA_HOST_DIR \
  FPGA_RUNTIME_DIR=$FPGA_RUNTIME_DIR \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME \
  FPGA_BIT_HOME=<HOST_RELEASE_DIR> \
  WORKLOAD=<WORKLOAD_DIR> \
  DIFF=<NEMU_SO> \
  CPU=<CPU> SUFFIX=<tag>
```

KMH/XiangShan defaults `UVHS_ILA_GATED_CLOCK` to
`fpga_top_debug.core_def.inter_soc_clk`; other profiles default to no gated
capture clock. Override it with the exact comma-separated names from
`query -capture` when a probe profile uses additional gated clocks.

By default, `run_host` uses the commands exported by `ila_host_env` to clear ILA
and stop the persistent UVHS runtime after the host exits. The upload hook
already clears ILA after a normal upload; the final clear covers interrupted or
non-upload paths. Set `FPGA_KEEP_RUNTIME=1` for consecutive runs; ILA is still
cleared but the runtime is retained.

Check or stop a retained session from its env-scripts checkout:

```sh
make -C env-scripts/fpga_diff runtime_status \
  FPGA_BACKEND=uvhs CPU=<CPU> SUFFIX=<tag> \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME

make -C env-scripts/fpga_diff runtime_stop \
  FPGA_BACKEND=uvhs CPU=<CPU> SUFFIX=<tag> \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME
```

When `FPGA_BACKEND=uvhs`, `run_host` automatically sets `FPGA_ILA_ARM_CMD` and
`FPGA_ILA_UPLOAD_CMD`. The generated upload hook restores the sign-off clock
and clears the trigger/capture state even when upload fails. Backend dispatch
and ILA hook construction stay inside `env-scripts`; playground decides where
to invoke those targets. For a split-host flow, `FPGA_RUNTIME` must also resolve
from `$FPGA_HOST` because host-side ILA and cleanup commands use it. Configure a
usable key on `$FPGA_HOST` or connect to it with agent forwarding.

The UVHS upload creates `UvData.usdb` and `UvData.vcd` under
`$FPGA_RUNTIME_HOME/runtime-work/UHD/uvhs_ila/` on the runtime host. The current
hook prints those remote paths but does not copy the files back to the FPGA host
or the machine that invoked `make run_host`.

With `USE_XDMA_H2C=1` (the default), the host writes only the workload `.bin`
to DDR through XDMA H2C before enabling the CPU DDR path. H2C has priority in
the memory controller, so no external `halt_soc` command is required. H2C does
not write the FPGA boot flash.

With `USE_XDMA_H2C=0`, the host writes DDR with external `FPGA_DDR_LOAD_CMD`:

```sh
make write_ddr \
  FPGA_BACKEND=uvhs \
  FPGA_HOST=$FPGA_HOST \
  FPGA_RUNTIME=$FPGA_RUNTIME \
  FPGA_RUNTIME_DIR=$FPGA_RUNTIME_DIR \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$FPGA_RUNTIME_DIR/ready-to-run/$WORKLOAD_TAG/$WORKLOAD_TAG.txt
```

### DDR Fallback / Debug Path

The direct `write_ddr` target is available for manual debugging and host builds
made with `USE_XDMA_H2C=0`; normal `run_host` uses H2C for DDR loading. UVHS
`write_ddr` uses `writemem -rtl` and keeps the CPU halted. The Vivado JTAG path
must likewise write DDR while the SoC is halted.

### Boot Flash Path

For designs that require a boot image in flash, write it after every
`write_bitstream`.

```sh
make write_flash \
  FPGA_BACKEND=uvhs \
  FPGA_HOST=$FPGA_HOST \
  FPGA_RUNTIME=$FPGA_RUNTIME \
  FPGA_RUNTIME_DIR=$FPGA_RUNTIME_DIR \
  FPGA_RUNTIME_HOME=$FPGA_RUNTIME_HOME \
  WORKLOAD=$FPGA_RUNTIME_DIR/ready-to-run/bootram.bin
```

## Next Steps

- For repository structure, see [layout.md](./layout.md).
- For workload customization, see [workload.md](./workload.md).
- If something fails, see [troubleshooting.md](./troubleshooting.md).
- For longer investigations, see [debug-flow.md](./debug-flow.md).
