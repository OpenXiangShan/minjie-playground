# FPGA DiffTest Walkthrough

This example assumes:

- `node004` is used for compiling XiangShan/NutShell Verilog, release, `fpga-host`, NEMU reference SO, and workloads
- `open103` is used for Vivado bitstream generation
- `node004` and `open103` share `/nfs`
- `fpga` is the FPGA host machine and does **not** share `/nfs`
- NFS repository path: `/nfs/home/youkunlin/workspace/FpgaDiff-playground`
- FPGA host repository path: `/home/fpga-v/youkunlin/FpgaDiff-playground`

The example uses XiangShan. For NutShell, replace the design argument with `nutshell`.

## 1. Build Verilog, Release, and Host on node004

Log in to `node004`:

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

make init

make clean xiangshan
make verilog xiangshan

make release xiangshan
export XS_RELEASE=$(cat build/release/latest-xiangshan.path)
export XS_RELEASE_NAME=$(cat build/release/latest-xiangshan.name)

make host xiangshan FPGA_HOST_HOME=$XS_RELEASE
```

The release directory is now at:

```sh
echo $XS_RELEASE
```

The default path looks like:

```text
/nfs/home/youkunlin/workspace/FpgaDiff-playground/build/release/20260407_XSTop_FpgaDiffDefaultConfig_FullDiff-noVec_ESBIFDU_012345
```

The trailing `012345` comes from the default `RELEASE_SUFFIX=HHMMSS`, which prevents overwrites.

Logs for Verilog, release, and host are in:

```text
build/build-log/
```

## 2. Generate Bitstream on open103

The Vivado environment on `open103` is already configured, so `REMOTE_ENV` is not needed:

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

make bit \
  xiangshan \
  REMOTE=open103 \
  REMOTE_DIR=/nfs/home/youkunlin/workspace/FpgaDiff-playground
```

Output is collected into:

```text
bitstream/xiangshan-YYYYmmdd-HHMMSS/
```

This directory contains `.bit`, `.ltx`, and the release directory used for synthesis. By default, the release pointed to by `build/release/latest-xiangshan.path` is used.

The Vivado log is written to the shared NFS at:

```text
build/build-log/bit-kmh-YYYYmmdd-HHMMSS.log
```

## 3. Build NEMU, Workload, and DDR txt

Still on the NFS repository:

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

export NEMU_CONFIG=riscv64-xs-ref-novec-nopmppma_defconfig
make nemu NEMU_CONFIG=$NEMU_CONFIG

make workload TARGET=linux/hello
```

Output files:

```text
ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so
ready-to-run/linux-hello/linux-hello.bin
ready-to-run/linux-hello/linux-hello.txt
```

Logs for NEMU, workload, and Bin2ddr:

```text
build/build-log/nemu-$NEMU_CONFIG-YYYYmmdd-HHMMSS.log
build/build-log/workload-linux-hello-YYYYmmdd-HHMMSS.log
```

## 4. Sync to FPGA Host

`fpga` does not share NFS. Copy the bitstream bundle and `ready-to-run/` to a fixed path on the remote machine. Replace `BIT_TAG` with the actual directory name from step 2:

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground
export NEMU_CONFIG=riscv64-xs-ref-novec-nopmppma_defconfig
export FPGA_ROOT=/home/fpga-v/youkunlin/FpgaDiff-playground
export BIT_TAG=xiangshan-YYYYmmdd-HHMMSS

ssh fpga "mkdir -p $FPGA_ROOT/bitstream $FPGA_ROOT/ready-to-run"
rsync -a --delete \
  bitstream/$BIT_TAG/ \
  fpga:$FPGA_ROOT/bitstream/$BIT_TAG/
rsync -a --delete ready-to-run/ fpga:$FPGA_ROOT/ready-to-run/
```

After sync, the key remote paths are:

```text
/home/fpga-v/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/$XS_RELEASE_NAME
/home/fpga-v/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/*.bit
/home/fpga-v/youkunlin/FpgaDiff-playground/bitstream/<bundle-name>/*.ltx
/home/fpga-v/youkunlin/FpgaDiff-playground/ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so
/home/fpga-v/youkunlin/FpgaDiff-playground/ready-to-run/linux-hello/linux-hello.bin
/home/fpga-v/youkunlin/FpgaDiff-playground/ready-to-run/linux-hello/linux-hello.txt
```

## 5. Write Bitstream, Write DDR, and Run Host on FPGA

Execute from the NFS repository via `REMOTE=fpga`:

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

export FPGA_ROOT=/home/fpga-v/youkunlin/FpgaDiff-playground
export BIT_TAG=xiangshan-YYYYmmdd-HHMMSS
export BIT_ROOT=$FPGA_ROOT/bitstream/$BIT_TAG
export XS_RELEASE_NAME=$(cat build/release/latest-xiangshan.name)
export NEMU_CONFIG=riscv64-xs-ref-novec-nopmppma_defconfig

make write_bitstream \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT

make write_jtag_ddr \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT \
  WORKLOAD=$FPGA_ROOT/ready-to-run/linux-hello/linux-hello.txt

make reset_cpu \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$BIT_ROOT
```

Run the host:

```sh
make run_host \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  HOST_BIN=$BIT_ROOT/$XS_RELEASE_NAME/difftest/build/fpga-host \
  HOST_ARGS="--diff $FPGA_ROOT/ready-to-run/$NEMU_CONFIG/riscv64-nemu-interpreter-so -i $FPGA_ROOT/ready-to-run/linux-hello/linux-hello.bin"
```

Logs are written locally by default:

```text
build/run-log/run-YYYYmmdd-HHMMSS.log
```
