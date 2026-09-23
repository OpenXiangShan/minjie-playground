# PC、ELF 与反汇编

本文件只说明二进制 authority、地址换算和指令回溯。checkpoint 配套 ELF 与 `vmlinux` 的常见目录见 [environment.md](environment.md)。

## 二进制 authority

checkpoint 的 `_memory_.zstd` 是内存镜像，不是可直接反汇编的 ELF。映射 PC 前确认：

- ELF 的 benchmark/input、构建版本、编译器和编译选项；
- ELF 是否为 PIE，以及运行时 load bias；
- 日志 PC 是虚拟地址、物理地址还是符号扩展后的地址；
- PC 位于用户态、内核态还是固件地址空间。

无法确认匹配 ELF 时，只报告指令编码和动态 trace，把符号与源码行标为未知。

## 提取 PC 附近指令

```bash
ELF=/path/to/matching/workload.elf
PC=0x00000000006e5a8c
riscv64-unknown-linux-gnu-objdump -d -S \
  --start-address=$((PC - 64)) --stop-address=$((PC + 64)) "$ELF"
riscv64-unknown-linux-gnu-addr2line -e "$ELF" -f -C "$PC"
```

工具链前缀以当前环境为准。PIE 先用内存映射或启动日志计算 ELF 虚拟地址。RISC-V compressed instruction 可能只有 2 字节，回溯前驱时使用反汇编边界或 commit trace，不固定减 4。

## 从首错回溯

1. 确认日志 PC 指向当前提交指令、参考模型指令还是报告差异的消费者。
2. 找出第一次产生错误 architectural state 的 producer。
3. GPR mismatch 沿 producer、旁路、写回和 rename/commit 映射回溯。
4. load/store 核对有效地址、宽度、mask、对齐、翻译和异常条件。
5. 控制流核对前一条 branch/jump、预测目标、实际目标和 redirect。
6. 异常/CSR 核对 privilege、cause、tval、epc 和 delegation。
