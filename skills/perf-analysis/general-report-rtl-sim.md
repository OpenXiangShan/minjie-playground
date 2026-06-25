# XiangShan RTL Simulator 性能计数分析指南

本文用于指导 agent 分析 XiangShan RTL 仿真日志 `simulator_err.txt`。目标不是罗列计数器，而是基于性能计数器建立“现象 -> 证据 -> 判断 -> 不确定项”的分析链，定位前端、后端、访存等模块的性能变化来源。

## 适用场景

当用户提供一个或多个 `simulator_err.txt`，或提供包含该文件的仿真结果目录时，按本文流程分析。若用户要求对比 base/new 或多个实验目录，默认输出对比报告，并同时给出关键计数器的原始值、标准化指标和变化幅度。

## 文件与阶段选择

`simulator_err.txt` 是 XiangShan 仿真过程中输出到 stderr 的运行日志和性能计数器集合。性能分析通常只使用性能计数器段，不把普通日志、warning、assert 信息当成性能数据。

同一个性能计数器通常出现两次：

| 出现顺序 | 含义 | 默认处理 |
| --- | --- | --- |
| 第一次 | warmup 阶段统计 | 不用于性能结论 |
| 第二次 | 正式仿真阶段统计 | 用于 IPC、MPKI、命中率、覆盖率等指标 |

默认规则：

1. 除非用户明确要求分析 warmup，否则使用正式仿真阶段计数器。
2. 若同名计数器出现多次，优先采用文件末尾、正式仿真阶段的值。
3. 不要把 warmup 和正式仿真的同名计数器相加。
4. 若无法判断阶段，必须在报告中说明该不确定性。

## 通用读取原则

1. 对比两个或多个结果时，先确认 benchmark、输入、仿真区间和配置开关是否可比。
2. 对百分比、命中率、准确率等派生指标，同时保留分子和分母。
3. 分母为 0 时，指标写为 `N/A`，不要强行写成 `0%`。
4. 所有绝对计数都应尽量标准化到 `cycles` 或 `committed instructions`。
5. 模块级结论必须同时检查上游和下游证据，避免把症状误判为根因。
6. 如果关键计数器缺失，先基于已有证据给出有限结论，再明确列出缺失计数器和需要补充的数据。

## 基础计数器语义

不同版本的 XiangShan 计数器名称可能不同。分析时按语义匹配，不要依赖单一固定名称。

| 类别 | 常见计数器语义 | 用途 |
| --- | --- | --- |
| 周期 | cycle、clock、perfCnt cycle | 计算 IPC、带宽、占比 |
| 提交 | committed instruction、commitInstr、instrCnt | 作为标准化分母 |
| 前端 | fetch、ifu、ftq、ittage、ras、ubtb、btb、tage | 判断取指和预测瓶颈 |
| 后端 | dispatch、issue、execute、writeback、commit、rob | 判断后端阻塞和执行瓶颈 |
| 访存 | load、store、lsq、ldq、stq、sbuffer | 判断访存指令、重放、阻塞 |
| Cache | l1、l2、l3、miss、hit、mshr、probe、refill | 计算命中率、MPKI 和访存压力 |
| TLB | itlb、dtlb、ptw、tlb miss | 判断地址翻译开销 |
| 预取 | prefetchSent、prefetchHit、prefetchLate、prefetchUseless | 评估预取效果 |

## 常用标准化指标

设：

```text
cycles = 正式仿真周期数
instrs = 正式仿真提交指令数
counter = 某计数器正式仿真值
```

常用指标：

| 指标 | 计算方式 | 说明 |
| --- | --- | --- |
| IPC | `instrs / cycles` | 整体性能主指标 |
| CPI | `cycles / instrs` | 每条指令平均周期 |
| per-cycle | `counter / cycles` | 吞吐、占用、事件密度 |
| per-kilo-instr | `counter * 1000 / instrs` | 每千指令事件数，常用于 miss |
| rate | `numerator / denominator` | 命中率、阻塞率、准确率等 |
| delta | `new - base` | 绝对变化 |
| delta% | `(new - base) / base` | 相对变化 |

对比输出默认包含 `base`、`new`、`delta`、`delta%`。若有多个实验，用一列显示 base，后续每个实验分别给出值和相对 base 的变化。

## 分析流程

### 1. 确认结果是否可比

先检查以下信息：

| 检查项 | 判断方式 |
| --- | --- |
| benchmark 是否一致 | 日志路径、命令行、workload 名称 |
| 仿真区间是否一致 | warmup、simpoint、max instruction、commit 数 |
| 配置是否一致 | core 参数、cache 参数、预取器、分支预测器、开关项 |
| 运行是否完整 | 是否正常结束，是否提前退出，是否包含 assert/fatal |

如果正式仿真提交指令数差异很大，应先解释原因，再做性能对比。若不能解释，报告中必须降低结论确定性。

### 2. 计算顶层性能

优先计算：

```text
IPC = committed instructions / cycles
CPI = cycles / committed instructions
```

若 IPC 下降，优先查找 `topdown`、`rob*wait*cycle` 等能够拆分等待周期的计数器，判断主导变化来自：

1. 前端供给不足。
2. 后端执行或资源受限。
3. 访存延迟或带宽压力。
4. 提交端阻塞或 flush 损失。

### 3. 分析前端

前端分析关注取指带宽、预测质量、前端缓冲和前端阻塞。

常见问题模式：

| 现象 | 可能原因 |
| --- | --- |
| fetch/commit 吞吐下降 | 前端供给不足或后端反压 |
| branch miss、redirect、flush 增加 | 分支预测准确率下降 |
| FTQ、fetch buffer、instruction buffer 空或满异常 | 前后端耦合问题 |
| ITLB miss、I-cache miss MPKI 增加 | 指令侧访存瓶颈 |

建议指标：

```text
branch MPKI = branch miss * 1000 / instrs
redirect MPKI = redirect count * 1000 / instrs
frontend stall ratio = frontend stall cycles / cycles
icache miss MPKI = icache miss * 1000 / instrs
```

### 4. 分析后端

后端分析关注 dispatch、issue、执行单元、ROB、提交阻塞。

常见问题模式：

| 现象 | 可能原因 |
| --- | --- |
| dispatch 阻塞增加 | ROB、IQ、LSQ、物理寄存器、重命名资源不足 |
| issue 吞吐下降 | 依赖链变长、功能单元竞争、唤醒选择问题 |
| ROB 满周期增加 | 长延迟操作或访存 miss 堵塞提交 |
| commit 吞吐下降 | 异常、flush、load violation、长延迟指令 |

建议指标：

```text
dispatch utilization = dispatch count / cycles
issue utilization = issue count / cycles
commit utilization = committed instructions / cycles
rob full ratio = rob full cycles / cycles
```

### 5. 分析访存系统

访存分析优先标准化到 MPKI、per-instr 或 per-cycle。

常见指标：

```text
load MPKI = load miss * 1000 / instrs
store MPKI = store miss * 1000 / instrs
l1 miss rate = l1 miss / l1 access
l2 miss rate = l2 miss / l2 access
mshr full ratio = mshr full cycles / cycles
replay MPKI = replay count * 1000 / instrs
```

建议判断顺序：

1. L1 miss 是否增加。
2. L2 miss 是否增加。
3. MSHR full、bank conflict、replay、nack 是否增加。
4. load-to-use 延迟或阻塞周期是否增加。
5. store buffer、store queue 是否产生反压。

若 L1 miss 增加但 L2 miss 不变，可能是层级间局部性变化、预取命中位置变化，或访问行为改变。若 L2 miss 也增加，继续检查预取、替换、带宽和内存侧压力。


## 对比报告模板

建议输出结构：

```text
结论：
- IPC 从 A 变为 B，变化 C%。
- 主要变化来自 X 模块：关键计数器 M 从 A 变为 B，MPKI/rate 变化 C。
- 次要影响包括 Y 和 Z。

顶层指标：
| 指标 | base | new | delta | delta% |

关键模块：
| 计数器/指标 | base | new | delta | delta% | 解释 |

根因判断：
1. 直接证据。
2. 支撑证据。
3. 仍需确认的反证或缺失计数器。
```

## 结论写法

结论应写成“指标变化 + 性能含义 + 证据链”，避免只罗列计数器。

示例：

```text
IPC 下降主要由 L2 侧访存压力增加导致。正式仿真阶段 L2 demand miss MPKI 上升，同时 MSHR full cycle ratio 增加，说明 miss 不只是数量增加，还造成了更强的并发资源阻塞。
```

证据不足时，明确说明：

```text
当前计数器能确认 L1 miss MPKI 增加，但无法区分是替换策略、预取污染还是访问流变化导致。需要补充 replacement、prefetch useless、prefetch late、MSHR occupancy 相关计数器。
```

## 常见陷阱

| 陷阱 | 正确处理 |
| --- | --- |
| 把 warmup 计数器用于结论 | 默认使用第二次出现的正式仿真计数器 |
| 只看绝对计数 | 用 cycles 或 committed instructions 标准化 |
| 只看 rate | 同时看分子和分母 |
| 只看 IPC | 建立前端、后端、访存证据链 |
| 分母为 0 时输出 0% | 输出 N/A |
| commit 数不一致仍直接对比 | 先解释仿真区间差异 |
| 预取命中率提高就判断变好 | 同时检查 demand miss、useless、late、drop 和带宽压力 |
| miss 增加就判断 Cache 变差 | 检查访问数、指令数、预取和上游行为是否变化 |

## 最小分析清单

对任意两个 `simulator_err.txt` 做性能对比时，至少给出：

1. 是否使用正式仿真阶段计数器。
2. committed instructions、cycles、IPC。
3. 变化最大的 MPKI 或 cycle ratio 指标。
4. 前端、后端、访存三类中哪一类最可能主导变化。
5. 关键证据表格。
6. 明确的不确定项和需要补充的计数器。

<!-- 当前内容尚比较粗糙，可在实践过程中分模块做细化的总结，如细化到具体的计数器名、具体的决策树 -->