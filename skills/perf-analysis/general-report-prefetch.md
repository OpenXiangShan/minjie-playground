# XiangShan 预取分析报告指南

本文用于指导 agent 分析 XiangShan 预取器相关性能计数器。报告目标是判断预取修改对 IPC、demand miss、命中覆盖、预取时效性、无用预取、丢弃请求以及下游 cache/memory 压力的影响。

其中 simulator_err.txt 格式参考 `base-simanalysis.md`。

## 预取器概况

当前香山预取器 library 与默认预取架构如下。实际分析时，以被测配置和日志中的计数器为准。

| 预取器名称 | 训练位置 | 预取位置 | 默认启用情况 |
| --- | --- | --- | --- |
| Stream | L1 | L1, L2 | 启用 |
| Stride | L1 | L1, L2 | 启用 |
| Berti | L1 | L1, L2 | 关闭 |
| SMS | L1 | L1, L2 | 启用 |
| VBOP | L2 | L2 | 启用 |
| PBOP | L2 | L2 | 启用 |
| TP | L2 | L2 | 启用 |
| NextLine | L2 | L2 | 关闭 |

## 重要计数器语义

计数器名称中的 `?` 表示 cache 层级，例如 `l1` 或 `l2`；`X` 表示具体预取器名称，例如 `Stream`、`Stride`、`SMS`。

| 计数器名称 | 含义 | 主要用途 |
| --- | --- | --- |
| `l?prefetchSent` | Prefetch request 发送总数 | 衡量预取流量 |
| `l?prefetchHit` | Demand request 命中预取块的总数 | 衡量预取减少 demand miss 的总数 |
| `l?demandMiss` | Demand request 未命中缓存的总数 | 表征真实 demand 侧 cache miss |
| `l?prefetchSentX` | 预取器 X 发送的 prefetch request 数量 | 衡量单个预取器流量 |
| `l?prefetchHitX` | Demand request 命中预取器 X 带来的预取块 | 计算单个预取器准确率和覆盖率 |
| `l?prefetchHitInCacheX` | Demand request 在 Cache 中命中预取器 X 带来的预取块 | 判断预取是否及时进入 Cache |
| `l?prefetchHitInMSHRX` | Demand request 进入 MSHR 时命中已有 MSHR 项，且该项来自预取器 X | 判断预取是否偏晚但仍有重叠 |
| `l?prefetchLateX` | 预取器 X 的 prefetch request 命中已有数据块或已有 MSHR 项 | 衡量晚到或重复预取 |
| `l?prefetchLateInCacheX` | 预取器 X 的 prefetch request 在 Cache 中命中已有数据块 | 衡量重复预取到已缓存数据 |
| `l?prefetchLateInMSHRX` | 预取器 X 的 prefetch request 在 MSHR 中命中已有 MSHR 项 | 衡量与已有 miss 的重叠 |
| `l?prefetchLateInCacheX_HitY` | 预取器 X 的 request 在 Cache 中命中预取器 Y 已带来的数据块 | 分析不同预取器之间的覆盖或重复 |
| `l?prefetchLateInMSHRX_HitY` | 预取器 X 的 request 在 MSHR 中命中预取器 Y 已产生的 MSHR 项 | 分析预取器之间的 MSHR 级重复 |
| `l?prefetchUselessX` | 预取器 X 取回的数据块未被 demand 使用就被替换 | 衡量无用预取和污染风险 |
| `l?prefetchDropByNackX` | 预取器 X 的 request 因资源不足或 nack 被丢弃 | 衡量资源压力和带宽竞争 |

## 核心指标

以 L1 Stream 为例：

```text
sent = l1prefetchSentStream
accuracy = l1prefetchHitStream / l1prefetchSentStream
coverage = l1prefetchHitStream / (l1prefetchHit + l1demandMiss)
lateRate = l1prefetchLateStream / l1prefetchSentStream
uselessRate = l1prefetchUselessStream / l1prefetchSentStream
dropRate = l1prefetchDropByNackStream / l1prefetchSentStream
```

通用规则：

1. 分母为 0 时输出 `N/A`。
2. accuracy 提高不一定代表性能变好，必须同时检查 coverage、demand miss、late、useless、drop 和 IPC。
3. sent 增加可能提升覆盖，也可能增加 cache/memory 压力。
4. useless 增加通常提示污染风险，但需要结合 demand miss 和替换相关计数器判断。
5. late 增加说明预取时机可能偏晚，也可能说明 demand 和 prefetch 对同一 miss 的重叠增加，需要结合 `HitInCache` 和 `HitInMSHR` 区分。

## 基本分析流程

### 1. 先看顶层影响

先比较 IPC、cycles、committed instructions，确认预取变化是否对应可见性能变化。若 IPC 无明显变化，仍可报告预取行为变化，但不要夸大为性能根因。

### 2. 分层统计 L1 和 L2

分别汇总 L1、L2 各个预取器的以下指标：

| 指标 | 含义 |
| --- | --- |
| demandMiss | demand 侧真实 miss 数量 |
| sent | 预取请求发送量 |
| accuracy | 预取请求被 demand 使用的比例 |
| coverage | 预取命中覆盖 demand miss 与 prefetch hit 总量的比例 |
| lateRate | 晚到或重复预取比例 |
| uselessRate | 未使用即被替换的比例 |
| dropRate | 因 nack 或资源不足被丢弃的比例 |

对比报告中至少给出 base/new/delta/delta%，并解释变化方向。

### 3. 判断收益或退化来源

优先使用以下证据链：

| 现象 | 倾向判断 | 需要补充确认 |
| --- | --- | --- |
| demandMiss 下降、coverage 上升、useless/drop 不明显增加 | 预取更有效 | 检查下游带宽是否变差 |
| accuracy 上升但 coverage 下降 | 预取更保守，覆盖不足 | 检查 sent 是否下降、demandMiss 是否上升 |
| sent 大幅上升且 useless/drop 上升 | 预取过激或资源竞争增强 | 检查 cache miss、MSHR full、memory bandwidth |
| lateRate 上升且 IPC 下降 | 预取时机偏晚或 miss 重叠不足 | 区分 late in cache 与 late in MSHR |
| dropRate 上升 | MSHR、队列或下游资源压力增加 | 检查 nack、MSHR full、bank conflict |

### 4. 结合下游压力

预取结论必须检查下游 cache/memory 压力，优先关注：

```text
L1/L2 demand miss MPKI
L1/L2 prefetch traffic per kilo instr
MSHR full cycle ratio
nack/drop count
bank conflict count
memory request bandwidth
replay MPKI
```

如果预取指标变好但 IPC 下降，优先怀疑带宽竞争、cache 污染、MSHR 占用或后端瓶颈掩盖。

## 输出要求

预取分析报告至少包含：

1. 顶层 IPC、cycles、committed instructions。
2. L1 和 L2 的 demandMiss、prefetchHit、prefetchSent 汇总。
3. 各预取器的 accuracy、coverage、lateRate、uselessRate、dropRate。
4. 下游 cache/memory 压力变化。
5. 明确结论：收益、退化、无明显影响，或证据不足。
6. 若证据不足，列出缺失计数器和下一步需要检查的方向。
