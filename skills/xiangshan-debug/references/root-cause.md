# 根因定位与修复验证

本文件用于一个失败用例的根因分析。它要求把架构差异追到第一个破坏微架构不变量的阶段，不把“最近的 commit”“代码相似”或“修复后暂时无报错”当作根因证据。

## 1. 固定首错和 producer

先从同一次 NEMU/difftest 运行保存：

- 首次差异的 PC、指令、提交计数、cycle、expected/actual 和完整错误文本；
- 最后一个有效提交组及其 lane 的 valid、PC、指令、ROB/队列身份；
- seed、checkpoint、配置、reference model 和 emu 的身份。

报告中的 `ABORT` 或 mismatch PC 可能只是发现差异的边界。沿错误寄存器或内存状态回溯到真正写入它的 producer；whole-register vector load 可能同时写多个向量寄存器。producer 必须由同次 commit trace 和匹配反汇编共同确认。

## 2. 沿真实阶段前向追踪

在首错前后的有限窗口逐阶段核对：

```text
dispatch/rename -> issue/read/forward -> execute/address generation
-> memory request/response -> writeback -> redirect/replay -> commit
```

每一阶段至少记录时间、动态身份（ROB/uop/request ID）、valid/ready/fire、关键输入和输出。结论按以下四类标记：

- `波形事实`：波形或日志直接给出的值；
- `源码语义`：同一 commit 的 Chisel/RTL 对字段含义的解释；
- `候选根因`：仍有替代解释的推断；
- `已验证根因`：已经能解释首错并由修复验证覆盖的条件。

对 redirect/rollback 类错误，必须同时抽取每个请求的 `valid`、ROB、恢复等级、目标 PC/FTQ 和来源元数据，再检查仲裁输出。以 `flushAfter`/`flush` 为例，同一 ROB 时应比较强度；修复必须选择强请求的完整 bundle，不能只把弱 bundle 的 level 改成强值而丢失来源字段。

## 3. 排除替代解释

至少检查并记录：

1. checkpoint、ELF、NEMU 和 seed 是否匹配；
2. waveform、RTL、源码 commit、生成物和配置是否一致；
3. 错误之前是否已有独立 mismatch、assertion 或 limit；
4. 波形时间轴是否与 difftest `cycleCnt` 同一基准；fork/checkpoint 波形的时间不能直接当作日志 cycle；
5. signal path、bit width、valid/ready 语义是否经过源码核对。

不能完成这些核对时，把结论写成“证据不足”，不要把相似 PC、统计计数或修复版正常退出升级为确定根因。

## 4. 最小修复与条件覆盖

只修改已证实的不变量，保留基线源码只读。fixed 版本除同一 checkpoint 的 difftest 回归外，应提供至少一种直接条件证据：cover print、计数器、断言或等价信号观测。证据要回答：

1. 原始触发条件确实在 fixed 运行中出现；
2. fixed 选择或输出满足预期不变量；
3. 原始首错位置被越过，完整 difftest 运行中的所有已提交指令都没有新的架构错误。

若条件没有命中或运行只到 limit，状态应为“验证不足/未完成”，不能写成通过。
