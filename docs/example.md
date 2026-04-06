# FPGA DiffTest 执行示例

这个例子假设：

- `node004` 用于编译 XiangShan/NutShell Verilog、release 和 `fpga-host`
- `open103` 用于 Vivado 生成 bitstream
- `node004` 和 `open103` 共享 `/nfs`
- `fpga` 是 FPGA 上位机，不共享 `/nfs`
- NFS 仓库路径是 `/nfs/home/youkunlin/workspace/FpgaDiff-playground`
- `fpga` 上位机仓库路径是 `/home/youkunlin/FpgaDiff-playground`

下面以 XiangShan / `kmh` 为例。NutShell 时把设计参数换成 `nutshell`，Vivado `CPU` 换成 `nutshell`。

## 1. 在 node004 编译 Verilog、release 和 host

登录 `node004`：

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

此时 release 位于：

```sh
echo $XS_RELEASE
```

默认形如：

```text
/nfs/home/youkunlin/workspace/FpgaDiff-playground/build/release/20260407_XSTop_FpgaDiffDefaultConfig_FullDiff-noVec_ESBIFDU_012345
```

最后的 `012345` 来自默认 `RELEASE_SUFFIX=HHMMSS`，用于避免重复。

Verilog、release、host 的日志在：

```text
build/build-log/
```

## 2. 在 open103 生成 bitstream

`open103` 的 Vivado 环境已经配置好，因此不需要额外设置 `REMOTE_ENV`：

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

make bit \
  REMOTE=open103 \
  REMOTE_DIR=/nfs/home/youkunlin/workspace/FpgaDiff-playground \
  CPU=kmh \
  CORE_DIR=$XS_RELEASE/build
```

输出会收集到：

```text
build/bitstream/kmh/
```

该目录下应包含 `.bit` 和 `.ltx`。

Vivado 日志也会写到共享 NFS 上的：

```text
build/build-log/bit-kmh-YYYYmmdd-HHMMSS.log
```

## 3. 构建 workload 并生成 DDR txt

仍在 NFS 仓库上执行：

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

make workload TARGET=linux/hello
```

输出文件：

```text
build/ready-to-run/linux-hello/linux-hello.bin
build/ready-to-run/linux-hello/linux-hello.txt
```

workload 和 Bin2ddr 的日志在：

```text
build/build-log/workload-linux-hello-YYYYmmdd-HHMMSS.log
```

## 4. 同步到 fpga 上位机

`fpga` 不共享 NFS，把顶层 `build` 下需要的内容同步到远端固定路径：

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

make sync_fpga \
  FPGA_REMOTE=fpga \
  FPGA_REMOTE_DIR=/home/youkunlin/FpgaDiff-playground
```

同步后远端关键路径为：

```text
/home/youkunlin/FpgaDiff-playground/build/release/$XS_RELEASE_NAME
/home/youkunlin/FpgaDiff-playground/build/bitstream/kmh
/home/youkunlin/FpgaDiff-playground/build/ready-to-run/linux-hello/linux-hello.bin
/home/youkunlin/FpgaDiff-playground/build/ready-to-run/linux-hello/linux-hello.txt
```

## 5. 在 fpga 上烧写、写 DDR、运行 host

在 NFS 仓库中通过 `REMOTE=fpga` 执行：

```sh
cd /nfs/home/youkunlin/workspace/FpgaDiff-playground

export FPGA_ROOT=/home/youkunlin/FpgaDiff-playground
export XS_RELEASE_NAME=$(cat build/release/latest-xiangshan.name)

make write_bitstream \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$FPGA_ROOT/build/bitstream/kmh

make write_jtag_ddr \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$FPGA_ROOT/build/bitstream/kmh \
  DDR_WORKLOAD=$FPGA_ROOT/build/ready-to-run/linux-hello/linux-hello.txt

make reset_cpu \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  FPGA_BIT_HOME=$FPGA_ROOT/build/bitstream/kmh
```

运行 host：

```sh
make run_host \
  REMOTE=fpga \
  REMOTE_DIR=$FPGA_ROOT \
  HOST_BIN=$FPGA_ROOT/build/release/$XS_RELEASE_NAME/difftest/build/fpga-host \
  HOST_ARGS="--diff $FPGA_ROOT/build/release/$XS_RELEASE_NAME/riscv64-nemu-interpreter-so -i $FPGA_ROOT/build/ready-to-run/linux-hello/linux-hello.bin"
```

日志默认写到远端：

```text
/home/youkunlin/FpgaDiff-playground/build/run-log/run-YYYYmmdd-HHMMSS-NNNNNNNNN.log
```
