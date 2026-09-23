# 输入与归档布局

本文件只说明常见路径结构和发现规则。路径选择优先级与源码使用规则以 [SKILL.md](../SKILL.md) 为准。

## SPEC checkpoint

checkpoint 根目录记为 `CHECKPOINT_ROOT`，常见层级是：

```text
CHECKPOINT_ROOT/
  <chekpoint-version>/
    checkpoint/
      <subbenchmark>/
        <instance>/
          <instance>_<weight>_memory_.zstd
```



举例：`/nfs/home/share/checkpoints_profiles/spec06_gcc16_rva23_novec_260820/checkpoint/astar_biglakes/10149/_10149_0.029776_memory_.zstd`
其中：
CHECKPOINT_ROOT: /nfs/home/share/checkpoints_profiles
<chekpoint-version>: spec06_gcc16_rva23_novec_260820
subbenchmark: astar_biglakes
instance: 10149
<instance>_<weight>_memory_.zstd：_10149_0.029776_memory_.zstd

文件名可能以zstd结尾，也可能是gz结尾。默认以zstd结尾。

SPEC CPU2017 的目录名可能包含编译选项和 input，不要按固定下划线数量解析。权重精度也可能不同，应联合 benchmark、checkpoint ID 和真实文件匹配：

```bash
: "${CHECKPOINT_ROOT:?Set CHECKPOINT_ROOT to the discovered checkpoint root}"
find "$CHECKPOINT_ROOT" -type f \
  -path '*/checkpoint/*' -name '*_memory_.zstd' | rg '/perlbench_checkspam/24520/'
```

SPEC17的例子：
 /nfs/home/share/checkpoints_profiles/spec17_rate_gcc16_rva23_novec_260904/checkpoint/500.perlbench_rate_refrate_00_checkspam.2500.5.25.11.150.1.1.1.1/11075/_11075_0.044852_memory_.zstd
 和
 /nfs/home/share/checkpoints_profiles/spec17_gcc16_rva23_novec_2harts_260911/checkpoint/bwaves_rate_refrate_00_bwaves_1/10017/_10017_0.0026158.gz


文件 CHECKPOINT_ROOT/<chekpoint-version>/checkpoint/checkpoint.lst 中记录了<checkpoint-version>的`检查点列表`：
格式为：<subbenchmark>_<instance> <subbenchmark>/<instance> 0 0 20 20
第二个<subbenchmark>/<instance>是关键信息，记录了检查点的路径

举例：
```
zeusmp_44100 zeusmp/44100 0 0 20 20
```

输出的布局和输入的布局类似
OUTPUT_ROOT/
  <subbenchmark>_<instance>_<weight>/
    simulator_err.txt
    simulator_out.txt

同一个香山在同一天运行的多个版本的检查点，输入日志会存放在相同的目录中，因此需要根据`检查点列表`确定输出日志的列表，避免混淆。

## 配套 ELF 与内核

当路径形如 `CPT_PATH/checkpoint` 时，配套文件通常位于：

```text
CPT_PATH/
  checkpoint/
  elf/
  kernel/
```

`elf/` 保存应用 ELF，`kernel/` 用于内核或系统进程地址。目录可能缺失或采用其他命名；必须核对 benchmark、input、构建版本和摘要。名称相近但版本不明的 ELF 不能替代。地址解释方法见 [disassembly.md](disassembly.md)。

## Weekly SPEC/perf-report

常见归档结构是：

```text
PERF_REPORT_ROOT/cr<date>-<short-sha>-<config>/
  riscv64-nemu-interpreter-so
  <flattened-checkpoint-name>/
    simulator_out.txt
    simulator_err.txt
    score.txt
    exit-code
```

stdout/stderr 也可能使用 `simulation_*` 拼写，部分文件可能不存在。目录存在但为空只表示产物缺失，不能推出仿真结果。

## PR EMU 归档

PR 的 Performance、Basics、Misc 和波形产物可能分别存放：

```text
<emu-performance-root>/<run_number>/
<emu-basics-root>/<run_number>/
<wave-archive-root>/<run_number>/
```

内部常见 `tar.gz`、`tar.zst`、`stdout.log`、`stderr.log`、FST 或 FSDB。归档根目录由用户、CI 配置或挂载信息确定，不能从其他环境猜测；远端运行与本地归档的关联规则见 [github-actions.md](github-actions.md)。

## emu 文件识别

- `build/emu` 通常是可变符号链接，归档前先用 `readlink -f` 解析；
- `build/verilator-compile/emu` 通常是 Verilator 产物；
- `build/gsim-compile/emu` 通常是已有归档中的 gsim 产物；仅用于识别和记录输入来源，禁止由本技能构建、生成、运行或复制为本轮调试 emu；
- 后端、源码 commit、配置、mtime 和摘要共同决定 emu 身份，文件名本身不足以证明来源。
