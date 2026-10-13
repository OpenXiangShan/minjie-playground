---
name: xiangshan-debug
description: >-
  调试一个给定的 XiangShan 失败用例：分类、复现、定位并修复 stuck、liveness、difftest mismatch、assertion、bad trap 或 fatal 问题。
  支持分析用户提供的 FSDB 现场，通过 eda01 的 Verdi 工具裁剪时间和信号并转为 VCD/FST。
  使用用户指定现场或任务目录内的日志和输入，从确认的官方 Git URL 获取指定 commit，构建带波形和 ChiselDB 的 Verilator emu，完成同一用例的修复和验证；任何情况下不构建、生成或运行 gsim emu。
---

# XiangShan 调试

本 skill 只处理用户指定的一个报错，走完输入核对、基线复现、波形定位、最小修复、同一用例验证和交付的全流程。始终区分日志事实、根因假设和验证结论。

## 核心约束

- 一个任务只对应用户或 `manifest.json` 指定的一个报错及其 workload/checkpoint。后续级联报错用于解释这个首错，不建立新任务。
- 所有 skill 产物直接写在当前任务根目录；不要创建 `cases/` 或其他类别目录。
- 只构建和运行 Verilator emu，并启用 waveform 和 ChiselDB、禁用 PGO。任何原因都不得构建、生成或运行 gsim emu；输入中已有的 gsim 只能记录来源。
- 编译和运行前设置 `NOOP_HOME=<当前使用的 XiangShan 根目录>`。
- 记录命令和环境时只保留调试所需的键名；`TOKEN`、`KEY`、`SECRET`、`PASSWORD`、`WEBHOOK`、`AUTH`、cookie 及授权头等敏感值必须替换为 `[REDACTED]`，不得把原始 `env` 或凭据写入任务产物。
- `XiangShan-original/` 是指定 commit 的冻结基线源码，用于初始调试 emu 和复现；`XiangShan/` 是从同一 commit 派生的唯一可变修复源码。
- `reproduction/` 只保存初始版本复现证据，`after-fix/` 只保存修复后 emu 和回归证据，构建日志只放在根目录的 `build-log/`。
- 不覆盖用户未提交改动、输入日志或已有报告，不用空文件代替缺失证据。
- 同一时刻只启动一次该用例的 emu invocation；仿真器内部的 LightSSS fork child 属于该次运行。编译并行度 `-j` 与 emu 线程数分别记录，不以重复启动仿真缩短等待。

## 输入和上下文边界

自动任务先读根目录的 `manifest.json`、`logs/` 和 `input/`。用户直接指定现场时，只从该现场补齐同样的元信息并写入 `execution.md`，不要求已有 manifest。确认报告名、workload、官方仓库 URL、branch、完整 commit、checkpoint、NEMU、原始 seed 和配置；源码从指定的官方 Git URL 获取，不依赖 monitor 的宿主机源码或 Git cache。

只使用当前任务提供的一个 workload 和它的错误日志。缺失的 checkpoint、NEMU、源码版本或日志必须在 `issues.md` 和分析报告中明确记录；不能用名称相似的文件代替。若原始日志已经包含 gsim 产物，只记录其来源，不把它作为本轮 emu。

用户提供 FSDB 现场时，记录原始波形路径、来源模拟器或 FPGA/RTL 版本、对应日志和 commit/config；按 [fsdb-waveform.md](references/fsdb-waveform.md) 提取证据。已有现场的导出结果保存到 `original/analysis/fsdb-export/`；它们用于分析原始失败，不代替 Verilator 基线复现或修复后验证。缺少来源版本时明确记录，不能将其内部信号直接归属到未经核实的源码。

`SKILL.md` 是主流程。链接的 reference 只在当前步骤需要其细节时读取；不要开始时一次性展开全部 reference，也不要把长日志、完整 `git status` 或整份源码搜索结果回显到上下文。写 Markdown 或 shell 脚本时，内容含反引号、`$()`、反斜杠或变量示例，使用带引号的 heredoc 或等价的不展开写法。

先在 `plan.md` 列出本用例的验收项：基线首错和错误波形、最早违反的不变量、patch、修复后条件覆盖、启用 difftest 的同用例验证。`execution.md` 持续记录实际命令、运行句柄和结果，`issues.md` 记录缺口与处理依据；不用重复状态更新代替新的证据。

## 工作流程

### 1. 获取基线源码并构建调试 emu

1. 从确认的官方 URL 获取源码到任务根目录的 `XiangShan-original/`，检出指定 commit 后，设置该目录的 `NOOP_HOME` 并先执行 `make -C XiangShan-original init`。使用该 commit 的标准初始化目标获取依赖，不用手动选择部分子模块代替；记录初始化日志和真实退出码，成功后核对嵌套子模块、导入的 build 文件及资源符号链接目标完整且匹配固定版本，再冻结源码并编译。不要使用 `init-force` 覆盖用户改动。短 commit 必须在该仓库中唯一解析；记录主仓、子模块 commit 与 dirty 状态，不能猜测版本。
2. 在第一次构建前检查 `logs/` 中的运行时初始化、配置路径和依赖提示（例如 `DRAMSIM3 config`、`DRAMSIM3_HOME`、Constantin 或 ChiselDB）。验证需要的本地路径和工具确实存在，确定与原始日志匹配的 build flags；缺失项先记录 blocker，不要先用缺依赖的默认配置启动一轮大编译。日志中只保留必要的键名和脱敏后的值。
3. 冻结基线源码，从它构建带波形和 ChiselDB 的 Verilator debug emu。记录 `CONFIG`、核数、emu 线程、DRAMSim3/Constantin 等开关、工具版本及运行配置文件摘要。常见选项为 `EMU_TRACE=fst WITH_CHISELDB=1`，准确接口以当前 commit 为准；禁用 PGO。
4. 完整构建 stdout/stderr 写入 `build-log/build-debug.log`，命令、必要环境、退出码和 emu 摘要写入 `execution.md`。退出码为 `0` 后仍确认实际二进制存在、可执行且来自 Verilator；归档前解析 `build/emu` 符号链接。

构建模板和低层检查见 [command-reference.md](references/command-reference.md)。

### 2. 分类这一个失败并确定复现目标

1. 对 `logs/` 做初筛，再读取首错前后的原始上下文。主类型为 `stuck`、`liveness`、`mismatch`、`assertion`、`bad_trap` 或 `fatal`。
2. 出现 `No instruction of core <id> commits for <cycles> cycles, maybe get stuck` 时，主类型必须是 `stuck`。REF 多执行一条指令后出现的 mismatch、`ABORT`、signal 或级联 assert 只能作为后续结果，不能覆盖首错。
3. 在根目录写 `checkpoints.txt`，记录这个任务提供的 checkpoint；固定字段为名称、`error_instrCnt`、`error_cycle` 和绝对路径。assertion 没有指令数时使用 `40000000`，没有 cycle 时写 `unknown`，并明确这不是日志观测值。
4. 在根目录写 `bug-analysis.md`，记录首错签名、粗分类、微架构归属、PC/cycle/instrCnt、expected/actual、输入摘要、版本和证据缺口。assertion 保留完整 message 与触发层级；mismatch 区分发现差异的 PC 与写入错误状态的 producer，不能把 ABORT PC 直接当成根因。
5. 为 code owner 更新根目录 `README.md`，先给出当前状态、失败场景和下一步；流程结束后将它更新为最终摘要。

### 3. 复现并分析波形

1. 使用基线 debug emu 和这一个 checkpoint。先查看 emu `--help` 和参数实现，使用原始 seed、NEMU 与匹配的运行配置；seed 缺失时显式记录选择，不能声称完整复刻原 CI。
2. 首次尝试写入根目录 `reproduction/`。如果需要同一 checkpoint 的有限重试或同一输入的参数变体，才使用 `reproduction/candidates/<attempt-slug>/`；这只是一个失败用例的尝试记录，不是第二个 case。
3. 日志、真实退出码和非空波形必须来自同一次 invocation，并核对本次首错签名和架构差异是否匹配。若当前版本支持 LightSSS，可用 `--enable-fork --fork-interval 60`；等待对应 child 完成写出再归档，不能选旧波形或仍在增长的文件。否则使用可验证的非 fork 波形参数。
4. 有失败 `instrCnt` 时将 `-I` 至少设为 `instrCnt + 10000`；只有 cycle 时设置 `-C cycle + 10000`；assertion 缺少指令数时使用 `40000000 + 10000`。不能凭空伪造代表波形。
5. 长时运行前记录预期执行范围和观察句柄。只有正常 limit 而无首错时，记为“未重现”；先检查配置、seed、后端和动态路径差异，只有新证据支持时才做一次有明确目标的参数重试。保留失败日志，不盲目扩到千万指令、反复减小余量或重跑相同命令。
6. 按实际格式读取波形：VCD/FST 使用当前 Python 环境的 `pywellen`；FSDB 先按 [fsdb-waveform.md](references/fsdb-waveform.md) 在 eda01 检查共享存储、读取 summary，以明确时间单位和窄信号层级导出 VCD/FST，再用 `pywellen` 查询。核对 timescale、有效时间范围及 commit/clock 锚点后做窄因果窗口分析；基线复现的查询保存到 `reproduction/analysis/`，用户提供现场的查询保存到 `original/analysis/`。缺少现成索引不代表波形不可读。

如果有依据的有限重试仍不能复现，记录“基线未重现”和每次参数差异，继续分析已有证据并列出下一步所缺的精确输入。仅靠静态分析提出的 patch 标为候选；修复版正常退出不能证明根因或完成修复，验证证据写入 `after-fix/validation/`。

波形格式选择与查询方法见 [waveform.md](references/waveform.md)，FSDB 裁剪、转换和校验见 [fsdb-waveform.md](references/fsdb-waveform.md)，运行模板见 [command-reference.md](references/command-reference.md)。

### 4. 隔离修复并回归

1. 从记录的原始 commit 建立任务根目录的 `XiangShan/`，不要修改 `XiangShan-original/`。
2. 从错误架构状态找到 producer，沿其实际生命周期定位“输入正确、输出首次错误”的阶段。记录时间、动态身份、有效信号、输入/输出、不变量及对应源码；检查 NEMU、checkpoint、配置、时间轴和信号误读等替代解释。方法见 [root-cause.md](references/root-cause.md)。
3. 修复已被证据支持的不变量；最近 commit、容量调整或源码相似性只能提示调查方向，不能成为直接 revert 的理由。运行 `git diff --check` 并构建同配置 fixed emu，完整输出写入 `build-log/build-fixed.log`。
4. 将基于原始 commit 的 patch 写入 `patch/patch.diff`，将建议的 Git commit title/message 写入 `patch/message.txt`。修复后的 emu 以普通文件形式保存为 `after-fix/new-emu`，不能用会被后续构建改写的符号链接。
5. 启用原 NEMU/difftest，运行同一 checkpoint、seed 和配置，结果写入 `after-fix/representative/`。必须实际越过原首错位置且没有原错误或新功能错误，并在完整运行日志中确认所有已提交指令没有架构状态 mismatch；记录终止原因和实际计数，正常 limit 只证明这个已执行范围。
6. 用定点波形、cover print、计数器或等价观测证明已证实的触发条件在 fixed 中命中，且输出满足不变量。观测不足时可增加验证 instrumentation，单独归档其 diff 和二进制身份；未命中条件时写“验证不足”，不能只凭无报错宣称修复。
7. 交付前用独立的证据清单重新核对首错、producer、波形窗口、patch 基准、同次运行关系和 fixed 结果，更新两个报告及 README。未完成项明确记录 blocker 和继续所需输入。

## 交付契约

任务根目录必须直接包含以下内容；所有链接使用相对路径并指向实际存在的产物：

```text
<task>/
  README.md                    # code owner 快速摘要，流程完成后更新
  plan.md                      # 输入范围、步骤、验收项
  execution.md                 # 命令、环境、退出码和阶段进度
  issues.md                    # 实际问题、阻塞和处理结果
  bug-analysis.md              # 这一个失败用例的完整根因分析和证据索引
  checkpoints.txt              # 这个输入的 checkpoint 定位信息
  report-bug-analysis.md       # 单个失败用例的分类、首错和根因总结
  report-fixed-analysis.md     # 单个失败用例的 patch 和回归总结
  XiangShan-original/          # 冻结基线源码
  XiangShan/                   # 私有修复源码
  build-log/
    build-debug.log
    build-fixed.log
  original/                     # 原始日志和输入已有的 old-emu（若有）
  reproduction/                # 初始 emu 的日志、波形和分析
  patch/
    patch.diff
    message.txt
  after-fix/                   # 修复 emu 和回归结果
```

`reproduction/candidates/`、`original/old-emu` 和 `after-fix/validation/` 只有在确有对应证据时创建。未进入修复阶段时不伪造 fixed emu 或 patch；报告写明实际状态。详细文件内容与通过门禁见 [reproduction-delivery.md](references/reproduction-delivery.md)。

## 操作边界

- 默认不执行 `git commit`，绝不执行 `git push`。
- 源码仓库、branch 和 commit 以 manifest 或用户指定现场中已核实的元信息为准；monitor 不把宿主机本地 XiangShan/NEMU/Git cache 路径写入 manifest，源码获取由任务自身完成。
- Python 使用当前项目或用户配置的环境，不在 skill 中假设固定虚拟环境路径。
- 清理前确认不会删除用户改动、唯一波形或失败现场。
- PR、trigger 和 Actions 产物关联见 [github-actions.md](references/github-actions.md)；PC 与 ELF 映射见 [disassembly.md](references/disassembly.md)。
