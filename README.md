# FpgaDiff Playground

This repository chains together the common FPGA DiffTest workflows:

```text
XiangShan / NutShell Verilog
  -> top-level difftest generates release / fpga-host
  -> env-scripts/fpga_diff generates Vivado bitstream
  -> NEMU generates reference SO
  -> workload-builder compiles workloads
  -> Bin2ddr generates DDR txt
  -> FPGA: write bitstream, write DDR, run fpga-host co-simulation
```

See [`docs/`](docs/README.md) for detailed guides. For DiffTest internals, see [`difftest/docs/`](difftest/docs/README.md).

## Output Directories

Build logs and releases go under `build/`, runtime inputs under `ready-to-run/`, bitstream bundles under `bitstream/`. All are gitignored:

| Path | Contents |
| --- | --- |
| `build/release/` | Release tarballs, unpacked releases, `latest-<design>.path`, `latest-<design>.name` |
| `build/build-log/` | Per-stage build logs: `verilog`, `release`, `host`, `bit`, `workload`, `nemu` |
| `build/run-log/` | `run_host` runtime logs (timestamped filenames) |
| `ready-to-run/<nemu-config>/` | `riscv64-nemu-interpreter-so` copied by `make nemu` |
| `ready-to-run/<target>/` | Workload `.bin` and Bin2ddr `.txt` |
| `bitstream/<design>-<time>/` | Bundle: `.bit/.ltx` and the release directory used for synthesis |

`RELEASE_SUFFIX` defaults to `HHMMSS` to prevent same-day overwrites. To suppress the suffix:

```sh
make release xiangshan RELEASE_SUFFIX=
```

The actual release path is parsed from `difftest/scripts/fpga/release.sh` output in `build/build-log/release-<design>-<time>.log`. `make release` unpacks the tarball to `build/release/<release-name>` and writes:

```text
build/release/latest-xiangshan.path
build/release/latest-xiangshan.name
```

Use `.path` for local operations; use `.name` to construct paths on remote hosts that do not share NFS.

## Initialization

```sh
make init
```

`init` runs top-level submodule init, each submodule's own `make init`, and `make -C Bin2ddr FPGA=1`.

`link_difftest` (included in `make init`) makes `XiangShan/difftest` and `NutShell/difftest` point to the top-level `difftest`. It does not modify `.gitmodules`, so it does not interfere with future pulls. If the internal difftest has local modifications, the link is refused.

## Verilog / Release / Host

The design must be specified explicitly:

```sh
make verilog xiangshan
make verilog nutshell
```

Typical XiangShan flow:

```sh
make clean xiangshan
make verilog xiangshan
make release xiangshan
XS_RELEASE=$(cat build/release/latest-xiangshan.path)
make host xiangshan FPGA_HOST_HOME=$XS_RELEASE
```

Build logs are written to `build/build-log/`.

Typical NutShell flow:

```sh
make clean nutshell
make verilog nutshell
make release nutshell
NUT_RELEASE=$(cat build/release/latest-nutshell.path)
make host nutshell FPGA_HOST_HOME=$NUT_RELEASE
```

`host` operates against a release directory, so `FPGA_HOST_HOME=<release-root>` is required. Both XiangShan and NutShell default to `RELEASE=1 FPGA=1 DIFFTEST_PERFCNT=1`.

## Vivado Bitstream

`bit` is the single top-level Vivado entry point. It runs `env-scripts/fpga_diff`'s `all` and `bitstream` targets, then collects `.bit/.ltx` and the release into `bitstream/<design>-<time>/`:

```sh
make bit xiangshan
```

Vivado can run on a remote host:

```sh
make bit \
  xiangshan \
  REMOTE=open103 \
  REMOTE_DIR=/nfs/home/youkunlin/workspace/FpgaDiff-playground
```

If the Vivado environment is already configured on `open103`, `REMOTE_ENV` is not needed.

The Vivado log is also written to the repository's `build/build-log/`. If `REMOTE_DIR` is on shared NFS, the log is directly visible locally.

By default, the release pointed to by `build/release/latest-<design>.path` is used, and `CORE_DIR` is set to that release's `build/`. To override:

```sh
make bit xiangshan BIT_SRC_DIR=/path/to/release
```

The output bundle looks like:

```text
bitstream/xiangshan-YYYYmmdd-HHMMSS/
bitstream/xiangshan-YYYYmmdd-HHMMSS/<release-name>/
bitstream/xiangshan-YYYYmmdd-HHMMSS/*.bit
bitstream/xiangshan-YYYYmmdd-HHMMSS/*.ltx
```

## NEMU Reference

`nemu` runs defconfig in `NEMU/`, compiles in parallel, and copies the reference SO to `ready-to-run/<NEMU_CONFIG>/`:

```sh
make nemu
```

Default config:

```text
riscv64-xs-ref-novec-nopmppma_defconfig
```

To switch configs:

```sh
make nemu NEMU_CONFIG=riscv64-nutshell-ref_defconfig
```

Default output:

```text
ready-to-run/riscv64-xs-ref-novec-nopmppma_defconfig/riscv64-nemu-interpreter-so
```

Log:

```text
build/build-log/nemu-<NEMU_CONFIG>-YYYYmmdd-HHMMSS.log
```

## Workload

`workload` compiles the program and places both `.bin` and `.txt` under `ready-to-run/<target>/`:

```sh
make workload TARGET=linux/hello
```

Default output:

```text
ready-to-run/linux-hello/linux-hello.bin
ready-to-run/linux-hello/linux-hello.txt
```

`TARGET` is passed directly to `workload-builder`, e.g., `linux/hello` or `am/<name>`. AM workloads default to the first `.bin` (sorted) under `package/bin/`.

See [`docs/workload.md`](docs/workload.md) for UART, device tree, and interrupt configuration.

## Sync to FPGA Host

If the FPGA host `fpga` does not share NFS, copy the bundle and `ready-to-run/` to a fixed remote path:

```sh
REMOTE_ROOT=/home/youkunlin/FpgaDiff-playground
BIT_TAG=xiangshan-YYYYmmdd-HHMMSS

ssh fpga "mkdir -p $REMOTE_ROOT/bitstream $REMOTE_ROOT/ready-to-run"
rsync -a --delete \
  bitstream/$BIT_TAG/ \
  fpga:$REMOTE_ROOT/bitstream/$BIT_TAG/
rsync -a --delete ready-to-run/ fpga:$REMOTE_ROOT/ready-to-run/
```

Key remote paths after sync:

```text
/home/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/<release-name>
/home/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/*.bit
/home/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/*.ltx
/home/youkunlin/FpgaDiff-playground/ready-to-run/<NEMU_CONFIG>
/home/youkunlin/FpgaDiff-playground/ready-to-run/<target>
```

## Flash and Run

Target names match `env-scripts/fpga_diff/Makefile`:

```sh
make write_bitstream FPGA_BIT_HOME=/path/to/bitstream-dir
make write_jtag_ddr FPGA_BIT_HOME=/path/to/bitstream-dir WORKLOAD=/path/to/workload.txt
make reset_cpu FPGA_BIT_HOME=/path/to/bitstream-dir
```

These commands support `REMOTE`. When running on the FPGA host, use the fixed remote path:

```sh
REMOTE_ROOT=/home/youkunlin/FpgaDiff-playground
BIT_TAG=xiangshan-YYYYmmdd-HHMMSS
BIT_ROOT=$REMOTE_ROOT/bitstream/$BIT_TAG

make write_bitstream \
  REMOTE=fpga \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT

make write_jtag_ddr \
  REMOTE=fpga \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$REMOTE_ROOT/ready-to-run/linux-hello/linux-hello.txt
```

`run_host` also supports `REMOTE`. Logs default to `build/run-log/run-YYYYmmdd-HHMMSS-NNNNNNNNN.log`:

```sh
XS_RELEASE_NAME=$(cat build/release/latest-xiangshan.name)
BIT_TAG=xiangshan-YYYYmmdd-HHMMSS
BIT_ROOT=/home/youkunlin/FpgaDiff-playground/bitstream/$BIT_TAG

make run_host \
  REMOTE=fpga \
  REMOTE_DIR=/home/youkunlin/FpgaDiff-playground \
  HOST_BIN=$BIT_ROOT/$XS_RELEASE_NAME/difftest/build/fpga-host \
  HOST_ARGS="--diff /home/youkunlin/FpgaDiff-playground/ready-to-run/riscv64-xs-ref-novec-nopmppma_defconfig/riscv64-nemu-interpreter-so -i /home/youkunlin/FpgaDiff-playground/ready-to-run/linux-hello/linux-hello.bin"
```
