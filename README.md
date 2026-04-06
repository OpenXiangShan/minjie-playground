# FpgaDiff Playground

这个仓库用于把 FPGA DiffTest 的常用流程串起来：

```text
XiangShan / NutShell Verilog
  -> 顶层 difftest 生成 release / fpga-host
  -> env-scripts/fpga_diff 生成 Vivado bitstream
  -> workload-builder 编译 workload
  -> Bin2ddr 生成 DDR txt
  -> FPGA 上烧 bit、写 DDR、运行 fpga-host 协同仿真
```

完整可执行示例见 `docs/example.md`。DiffTest 细节可参考 `difftest/docs/`。

## 产物目录

顶层生成物统一放在 `build/`，该目录已加入 `.gitignore`：

| 路径 | 内容 |
| --- | --- |
| `build/release/` | release tarball、解包后的 release、`latest-<design>.path`、`latest-<design>.name` |
| `build/ready-to-run/<target>/` | workload `.bin` 和 Bin2ddr 转出的 `.txt` |
| `build/bitstream/<cpu>/` | Vivado 生成后收集出的 `.bit` 和 `.ltx` |
| `build/build-log/` | `verilog`、`release`、`host`、`bit`、`workload` 等构建阶段日志 |
| `build/run-log/` | `run_host` 的运行日志，默认文件名带时间戳 |

`RELEASE_SUFFIX` 默认是当前时间 `HHMMSS`，用于避免同一天同配置 release 覆盖。需要隐藏 suffix 时可以显式传空值：

```sh
make release xiangshan RELEASE_SUFFIX=
```

release 的实际路径由 `difftest/scripts/fpga/release.sh` 的日志输出解析得到，日志位于 `build/build-log/release-<design>-<time>.log`。`make release` 会把 release tarball 解到 `build/release/<release-name>`，并写入：

```text
build/release/latest-xiangshan.path
build/release/latest-xiangshan.name
```

本机继续使用 release 时读 `.path`；同步到不共享 NFS 的上位机后，用 `.name` 拼远端路径更可靠。

## 初始化

```sh
make init
```

`init` 会执行顶层 submodule init、各子模块自己的 `make init`，并执行 `make -C Bin2ddr FPGA=1`。

`link_difftest` 会让 `XiangShan/difftest` 和 `NutShell/difftest` 指向顶层 `difftest`，并已包含在 `make init` 里。它不修改 XS/NutShell 的 `.gitmodules`，所以不影响后续 pull 更新；如果内部 difftest 有本地修改，会拒绝替换。

## Verilog / Release / Host

设计不再有默认值，必须显式传入：

```sh
make verilog xiangshan
make verilog nutshell
```

香山常用流程：

```sh
make clean xiangshan
make verilog xiangshan
make release xiangshan
XS_RELEASE=$(cat build/release/latest-xiangshan.path)
make host xiangshan FPGA_HOST_HOME=$XS_RELEASE
```

这些构建阶段的日志会写到 `build/build-log/`。

NutShell 常用流程：

```sh
make clean nutshell
make verilog nutshell
make release nutshell
NUT_RELEASE=$(cat build/release/latest-nutshell.path)
make host nutshell FPGA_HOST_HOME=$NUT_RELEASE
```

`host` 只面向 release 目录运行，因此需要显式传 `FPGA_HOST_HOME=<release-root>`。无论 XiangShan 还是 NutShell，默认参数都是 `RELEASE=1 FPGA=1 DIFFTEST_PERFCNT=1`。

## Vivado Bitstream

`bit` 是唯一的顶层 Vivado 生成入口，内部会执行 `env-scripts/fpga_diff` 的 `all` 和 `bitstream`，然后把 `.bit/.ltx` 收集到 `build/bitstream/<cpu>/`：

```sh
make bit CPU=kmh CORE_DIR=$XS_RELEASE/build
```

Vivado 可放到远端执行，例如 `open103`：

```sh
make bit \
  REMOTE=open103 \
  REMOTE_DIR=/nfs/home/youkunlin/workspace/FpgaDiff-playground \
  CPU=kmh \
  CORE_DIR=$XS_RELEASE/build
```

`open103` 的 Vivado 环境若已配置好，不需要额外传 `REMOTE_ENV`。

Vivado 生成日志也会写到远端仓库的 `build/build-log/`，如果 `REMOTE_DIR` 在共享 NFS 上，本机可以直接查看。

## Workload

`workload` 会编译程序，并把 `.bin` 和 `.txt` 都放到 `build/ready-to-run/<target>/`：

```sh
make workload TARGET=linux/hello
```

默认输出：

```text
build/ready-to-run/linux-hello/linux-hello.bin
build/ready-to-run/linux-hello/linux-hello.txt
```

如果 `TARGET` 不带类型，默认按 Linux workload 处理；AM workload 也支持，默认取 `package/bin/` 下排序后的第一个 `.bin`。

## 同步到 FPGA 上位机

如果上位机 `fpga` 不共享 NFS，可以把 `build/release`、`build/ready-to-run` 和 `build/bitstream` 同步到远端固定路径：

```sh
make sync_fpga \
  FPGA_REMOTE=fpga \
  FPGA_REMOTE_DIR=/home/youkunlin/FpgaDiff-playground
```

同步后远端目录结构仍是：

```text
/home/youkunlin/FpgaDiff-playground/build/release
/home/youkunlin/FpgaDiff-playground/build/ready-to-run
/home/youkunlin/FpgaDiff-playground/build/bitstream
```

## 烧写和运行

target 名称与 `env-scripts/fpga_diff/Makefile` 保持一致：

```sh
make write_bitstream FPGA_BIT_HOME=/path/to/bitstream-dir
make write_jtag_ddr FPGA_BIT_HOME=/path/to/bitstream-dir DDR_WORKLOAD=/path/to/workload.txt
make reset_cpu FPGA_BIT_HOME=/path/to/bitstream-dir
```

这些命令支持 `REMOTE`。在 `fpga` 上位机运行时，推荐使用远端固定路径：

```sh
REMOTE_ROOT=/home/youkunlin/FpgaDiff-playground

make write_bitstream \
  REMOTE=fpga \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$REMOTE_ROOT/build/bitstream/kmh

make write_jtag_ddr \
  REMOTE=fpga \
  REMOTE_DIR=$REMOTE_ROOT \
  FPGA_BIT_HOME=$REMOTE_ROOT/build/bitstream/kmh \
  DDR_WORKLOAD=$REMOTE_ROOT/build/ready-to-run/linux-hello/linux-hello.txt
```

`run_host` 也支持 `REMOTE`，默认日志写到远端 `build/run-log/run-YYYYmmdd-HHMMSS-NNNNNNNNN.log`：

```sh
XS_RELEASE_NAME=$(cat build/release/latest-xiangshan.name)

make run_host \
  REMOTE=fpga \
  REMOTE_DIR=/home/youkunlin/FpgaDiff-playground \
  HOST_BIN=/home/youkunlin/FpgaDiff-playground/build/release/$XS_RELEASE_NAME/difftest/build/fpga-host \
  HOST_ARGS="--diff /path/to/ref-so -i /home/youkunlin/FpgaDiff-playground/build/ready-to-run/linux-hello/linux-hello.bin"
```
