# XiangShan Fpga Without DiffTest

[中文](README.zh-CN.md)

This flow targets XiangShan on the `kunminghu-v2` submodule revision. `NO_DIFF=1` is supported for XiangShan only.

## Generate RTL

```bash
make verilog xiangshan \
  XS_CONFIG=KunminghuV2Config \
  YAML_CONFIG=$PWD/docs/Fpga/openllc-1M.yml \
  XS_DEBUG_ARGS=--disable-always-basic-diff
```

These options select `CONFIG=KunminghuV2Config`, apply [openllc-1M.yml](openllc-1M.yml) to configure a 1 MiB OpenLLC with one bank, eight ways, and 2048 sets, and disable the always-on basic DiffTest instrumentation. The generated top is `XSTop`, rather than the DiffTest-oriented `SimTop`. `NO_DIFF` is not needed until project generation.

## Package Fpga RTL

Reuse DiffTest's existing `fpga-release` flow after generating `XSTop`:

```bash
make release xiangshan RELEASE_SUFFIX=nodiff
```

The playground target invokes the underlying command below, then extracts the archive and records it as the latest XiangShan release:

```bash
mkdir -p build/release
NOOP_HOME=$PWD/XiangShan \
  make -C XiangShan/difftest fpga-release \
    RELEASE_DIR=$PWD/build/release RELEASE_SUFFIX=nodiff
```

`fpga-release` copies `XiangShan/build/` first and applies the existing depth-greater-than-4000 URAM replacement only to the release copy's `build/rtl/array_*.v` files. The generated XiangShan RTL remains unchanged.

## Build A Bitstream

Run Vivado in the current playground worktree:

```bash
make bit xiangshan NO_DIFF=1 SUFFIX=nodiff
```

The Fpga project is named `fpga_kmh-nodiff`. It consumes `build/rtl` from the latest extracted `fpga-release`, including the release flow's URAM attributes.

## Build A Workload

The following command builds a small AM workload and converts it to the JTAG DDR text format under `ready-to-run/xiangshan-am-hello/`:

```bash
make workload xiangshan TARGET=am/hello
```

## Program And Run

Program on the Fpga host, halt the SoC before writing DDR, then release reset. The XDMA/fpga-host path is intentionally unavailable in this mode.

```bash
make write_bitstream NO_DIFF=1 FPGA_BIT_HOME=/path/to/bitstream
make -C env-scripts/fpga_diff halt_soc \
  FPGA_BIT_HOME=/path/to/bitstream
make write_jtag_ddr \
  FPGA_BIT_HOME=/path/to/bitstream \
  WORKLOAD=ready-to-run/xiangshan-am-hello
make reset_cpu FPGA_BIT_HOME=/path/to/bitstream
```
