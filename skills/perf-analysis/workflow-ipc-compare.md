# IPC 对比性能分析工作流

本文用于指导 agent 分析多个 XiangShan 性能计数器结果目录。用户通常会提供类似 `base=<dir0> exp1=<dir1> exp2=<dir2>` 的参数，每个目录中记录了修改前后 SPEC CPU2006 各检查点的性能测试结果。

结果目录示例：`/nfs/home/cirunner/perf-report-custom/cr260519-064f8462a-CHIConfig`，其中 `064f8462a` 通常是该目录对应的 commit。若目录名中无法解析 commit，需要从用户给定上下文或仓库状态中确认；无法确认时，在报告中说明。

## 1. 生成 IPC 排序表

在 minjie-playground 仓库中执行：

```bash
ANAL_DIR=<your-minjie-playground-path>
python3 $ANAL_DIR/env-scripts/perf/ipc_diff_pro.py \
  /nfs/home/share/checkpoints_profiles/spec06_gcc15_rv64gcb_base_260122/checkpoint-0-0-0/cluster-0-0.json \
  base=<dir0> exp1=<dir1> exp2=<dir2> \
  -o ipc-compare.csv -j8
```

要求：

1. `<your-minjie-playground-path>` 使用当前仓库绝对路径。
2. `base=<dir0>`、`exp1=<dir1>` 等参数保持用户提供的命名。
3. 若命令失败，先记录错误信息，再检查路径、权限和输入目录结构。

`ipc-compare.csv` 会按 IPC 变化绝对值从大到小输出检查点信息。常见列含义如下：

| 列 | 含义 |
| --- | --- |
| 检查点名称列 | 如 `gcc_expr2_5858_0.0323863`。第一个 `_` 前通常是 benchmark 名称，最后一个 `_` 后通常是权重 |
| 实验 IPC 列 | 各实验的 IPC 数值，例如 `1.3677760562035624` |
| IPC 增幅列 | 实验相对 base 的 IPC 变化，例如 `0.4789296695484957`；排序通常按绝对值从大到小 |

## 2. 选择重点分析对象

从 `ipc-compare.csv` 中选择重点检查点：

1. 优先选择权重大于 `0.1` 的检查点。
2. 优先选择 IPC 减幅最大的三个不同 benchmark。
3. 如果不足三个 benchmark，说明筛选结果，并分析现有符合条件的对象。
4. 如果用户明确关注 IPC 增幅或特定 benchmark，以用户要求为准。

每个检查点对应的日志路径为 `<dir>/<checkpoint-name>/simulator_err.txt`，如 `text
/nfs/home/cirunner/perf-report-custom/cr260515-d097c4ede-CHIConfig/gcc_expr2_5858_0.0323863/simulator_err.txt`。

## 3. 分析 simulator_err.txt

对选中的每个检查点，按以下流程分析：

1. 参考 `skills/perf-analysis/general-report-rtl-sim.md` 完成通用 RTL 仿真性能分析。
2. 如涉及预取器，参考 `skills/perf-analysis/general-report-prefetch.md` 补充预取专项分析。
3. 对每个实验目录横向比较同一 benchmark 的关键计数器。
4. 对不同 benchmark 纵向比较相同指标是否呈现一致趋势。
5. 所有可能原因必须有 `simulator_err.txt` 中的计数器数值支持。

报告中不要只写“可能是某模块导致”。必须给出支撑证据，例如 IPC、MPKI、cycle ratio、accuracy、coverage、drop、stall cycle 等指标的 base/new 差异。

## 4. 结合 commit diff

根据各实验目录对应 commit 的 git diff，确认修改涉及的功能或性能逻辑，并据此做针对性分析：

1. 提取 base 与实验 commit。
2. 查看相关 diff，识别修改模块。
3. 在性能计数器中重点检查修改模块及上下游模块。
4. 报告必须说明修改相关模块的计数器变化如何影响 IPC。

如果无法访问对应仓库或 diff，报告中明确说明无法确认代码改动，只基于计数器给出结论。

## 5. 报告输出

最终生成一份 Markdown 分析报告，路径为：

```text
<prj_path>/yymmdd-xxx-rpt.md
```

命名要求：

1. `yymmdd` 使用当前日期，例如 2026 年 6 月 17 日写作 `260617`。
2. `xxx` 使用任务简称，尽量短且能表达主题。
3. `rpt` 表示 report。

报告至少包含：

1. 输入目录、对应 commit、分析日期。
2. IPC 排序表摘要和重点检查点选择依据。
3. 每个重点 benchmark 的顶层 IPC/cycles/instructions 对比。
4. 关键模块计数器对比表。
5. 结合 diff 的原因分析。
6. 跨 benchmark 的共同趋势和差异。
7. 最终结论、证据强度和仍需补充的信息。
