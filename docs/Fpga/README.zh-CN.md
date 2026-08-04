# 香山 Fpga 无 DiffTest 流程

[English](README.md)

本流程面向 `kunminghu-v2` 子模块版本的香山处理器。`NO_DIFF=1` 目前仅支持香山。

## 生成 RTL

```bash
make verilog xiangshan \
  XS_CONFIG=KunminghuV2Config \
  YAML_CONFIG=$PWD/docs/Fpga/openllc-1M.yml \
  XS_DEBUG_ARGS=--disable-always-basic-diff
```

这些选项会选择 `CONFIG=KunminghuV2Config`，通过 [openllc-1M.yml](openllc-1M.yml) 将 OpenLLC 配置为 1 MiB、1 个 bank、8 路组相联和 2048 个 set，并关闭始终启用的基础 DiffTest 插桩。生成的顶层模块是 `XSTop`，而不是面向 DiffTest 的 `SimTop`。直到生成 Fpga 工程时才需要设置 `NO_DIFF`。

## 打包 Fpga RTL

生成 `XSTop` 后，复用 DiffTest 已有的 `fpga-release` 流程：

```bash
make release xiangshan RELEASE_SUFFIX=nodiff
```

playground 会调用以下底层命令，然后解压归档，并将其记录为最新的香山 release：

```bash
mkdir -p build/release
NOOP_HOME=$PWD/XiangShan \
  make -C XiangShan/difftest fpga-release \
    RELEASE_DIR=$PWD/build/release RELEASE_SUFFIX=nodiff
```

`fpga-release` 会先复制 `XiangShan/build/`，然后只在 release 副本中的 `build/rtl/array_*.v` 文件上执行已有的深度大于 4000 的 URAM 替换。香山生成目录中的 RTL 保持不变。

## 生成 Bitstream

在当前 playground worktree 中运行 Vivado：

```bash
make bit xiangshan NO_DIFF=1 SUFFIX=nodiff
```

生成的 Fpga 工程名为 `fpga_kmh-nodiff`。它使用最新解压的 `fpga-release` 中的 `build/rtl`，其中包含 release 流程添加的 URAM 属性。

## 编译 Workload

以下命令会编译一个简单的 AM workload，并将其转换成 JTAG DDR 使用的文本格式，输出到 `ready-to-run/xiangshan-am-hello/`：

```bash
make workload xiangshan TARGET=am/hello
```

## 烧写和运行

在 Fpga 主机上烧写 bitstream。写入 DDR 前先暂停 SoC，写入完成后再释放复位。本模式不支持 XDMA/fpga-host 路径。

```bash
make write_bitstream NO_DIFF=1 FPGA_BIT_HOME=/path/to/bitstream
make -C env-scripts/fpga_diff halt_soc \
  FPGA_BIT_HOME=/path/to/bitstream
make write_jtag_ddr \
  FPGA_BIT_HOME=/path/to/bitstream \
  WORKLOAD=ready-to-run/xiangshan-am-hello
make reset_cpu FPGA_BIT_HOME=/path/to/bitstream
```
