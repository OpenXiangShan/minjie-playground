---
name: xiangshan-debug
description: >-
  分类、复现并修复 XiangShan 在 SPEC CPU 检查点或少量 workload 中暴露的 stuck、liveness、difftest mismatch、assertion、bad trap、fatal 等问题。
  使用本地日志、源码或 Git commit 构建带波形和 ChiselDB 的 Verilator emu，按错误类型选择代表 checkpoint，隔离修复并回归；任何情况下不构建、生成或运行 gsim emu。
---

# XiangShan 调试

把失败日志或运行现场推进为：错误分类、可复现现场、根因与 patch、修复后回归。始终区分日志事实、初步归类、根因假设和验证结论。

## 核心约束

- 只构建和运行 Verilator emu，并启用 waveform 和 ChiselDB、禁用 PGO。任何原因都不得构建、生成或运行 gsim emu；输入中已有的 gsim 只能记录来源。
- 编译和运行前设置 `NOOP_HOME=<XiangShan 根目录>`。
- 任务级只保留一份共享初始源码 `XiangShan-original/`，与 `cases/` 同级。复现使用该源码；修复使用各类别私有的 `XiangShan/`。
- 同一错误类型只建立一个类别目录。每类最多确定一个最终代表 checkpoint；初始 Verilator 最多尝试 5 个候选。
- `reproduction/` 只保存初始版本复现产物，`after-fix/` 只保存修复后 emu 和回归产物，构建日志只放在 `build-log/`。
- 不覆盖用户未提交改动、输入日志或现有报告，不用空文件代替缺失证据。

## 识别输入

先确认日志、checkpoint、原 emu、XiangShan 源码或 commit、workload ELF、`vmlinux` 和 NEMU 的真实路径。缺失项必须记录，不能用名称相似的文件代替。

本地信息优先：

1. 用户提供本地运行目录时，先检查该目录的日志、元数据和目录名。
2. `cr<日期>-<短 commit>-<配置>` 可提供候选 commit。例如 `cr260917-c8d7b3a5c-DefaultConfig` 对应候选 `c8d7b3a5c`；使用前必须在源码仓库中解析为唯一完整 commit。
3. 本地日志可用，且已有源码路径或可验证 commit 时，不解析用户同时提供的 GitHub PR、trigger 或 Actions run 链接。
4. 只有本地信息不能定位日志或源码版本时，才使用远端链接补齐缺失信息。

批量 SPEC 日志和少量 workload 使用相同的分类、复现和证据规则。

## 任务的顺序和子agent调度

先执行第一部分和第二部分，后执行第三部分和第四部分, ：
第一、二部分没有数据依赖，应使用两个子 agent 并行处理：一个准备并构建源码，一个分类日志和准备现场。分类任务不能修改正在构建的源码或构建目录。
第三、四部分有数据依赖，应在第一、二部分完成后顺序处理。
每一个错误类型的第三部分和第四部分是独立的，调用子agent提高处理的并发度。

## 第一部分：准备源码并构建调试 emu

1. 用户提供本地源码时，把它作为 `XiangShan-original/` 的来源。记录绝对路径、主仓与子模块 commit、工作区状态和构建配置，不覆盖未提交改动。
2. 没有本地源码但有可验证 commit 时，只获取一份仓库到 `XiangShan-original/`，检出该 commit 并初始化子模块。优先使用用户指定仓库，否则使用 `https://github.com/OpenXiangShan/XiangShan.git`。
3. 短 commit 必须唯一解析；无法解析或存在歧义时记录证据，不能猜测版本。
4. 从 `XiangShan-original/` 只构建一份共享调试 Verilator emu。常见核心选项为 `EMU_TRACE=1 WITH_CHISELDB=1`，准确选项以当前源码为准。
5. 保存构建命令、环境、退出码、完整 stdout/stderr、emu 真实路径和摘要。退出码为 `0` 后仍要确认 emu 存在、可执行。
6. 每个类别的 `build-log/build-debug.log` 保存共享调试构建日志的现场副本；不得为不同类别重复构建初始源码。

构建、运行和 patch 检查的命令模板见 [command-reference.md](references/command-reference.md)，运行环境和产物发现见 [environment.md](references/environment.md)。

## 第二部分：分类并准备现场

### 首错分类

1. 对全部日志运行 `scripts/triage_logs.py` 初筛，再读取每个候选首错前后的原始上下文。
2. 主类型包括 `stuck`、`liveness`、`mismatch`、`assertion`、`bad_trap` 和 `fatal`。
3. 出现 `No instruction of core <id> commits for <cycles> cycles, maybe get stuck` 时，主类型必须是 `stuck`，不能归入 `liveness`。
4. REF 多执行一条指令后产生的 mismatch、`ABORT`、signal 或级联 assert 只作为后续结果，不能覆盖首错。

### 合并规则

- 跨全部输入、版本、配置和 checkpoint 合并相同主错误类型；不能因来源不同建立多个同类目录。
- `assertion` 必须提取完整 message，去掉日志前缀和外层运行位置字段，并统一连续空白。
- 仅把十进制/十六进制数字、地址、ID、计数值和行号等实例数字归一化为 `<NUM>`。
- 归一化后的非数字文本或数字 token 的语义位置不同，视为不同错误类型；仅少量数字实例值不同，视为同一类型。
- 原始 message、归一化模板和合并或拆分依据写入 `bug-analysis.md`。

### 清单和候选

1. `checkpoints.txt` 列出该类全部 checkpoint，固定字段为名称、`error_instrCnt`、`error_cycle` 和绝对路径。
2. `assertion` 日志没有指令数时，使用默认 `error_instrCnt=40000000`；没有 cycle 时写 `unknown`。在 `bug-analysis.md` 标明默认值不是日志观测值。
3. 每类标注为前端取指、乱序调度或访存子系统之一。
4. 初始候选默认选择失败 cycle 最少的 checkpoint；cycle 不可比时使用 `instrCnt`，仍不可比时记录选择依据。
5. 初始候选不是最终代表。若不能复现，按出错节点的执行周期数 cycle 由小到大排序继续尝试，同类累计最多 5 个。

### 类别目录

- 每类只建立一个 `<failure-type>-<count>-<test-case>-<checkpoint>` 目录，标签转为稳定英文 slug。
- 目录初始使用预选候选命名；其他候选成为最终代表时，只允许重命名这一个目录一次。
- 5 个候选均不能复现时，保留初始目录名并标记无可复现代表，不得创建第二个类别目录。
- 每类必须有供 code owner 快速 review 的 `README.md`；完整根因推理写入 `bug-analysis.md`。

分类证据见 [failure-taxonomy.md](references/failure-taxonomy.md)，目录、README、`checkpoints.txt` 和报告契约见 [reproduction-delivery.md](references/reproduction-delivery.md)。

## 第三部分：复现并生成波形

1. 使用 `XiangShan-original/` 的共享 debug emu，从预选候选开始运行。
2. 候选未复现首错时，按既定顺序继续尝试；包含首个候选最多 5 个。第一个稳定复现首错的 checkpoint 才是最终代表。
3. 每个候选使用独立的 `reproduction/candidates/<checkpoint-slug>/`，保存准确命令、环境、stdout、stderr 和退出码。
4. 复现成功后，才把该候选的日志和波形固化为 `reproduction/` 根部的最终代表证据。不能拼接旧日志和新波形。
5. 运行前查看 emu `--help`，启用 `--enable-fork`、固定 seed，并使用当前版本支持的波形参数。波形覆盖首错前因果窗口和首错后的最小观察窗口。

运行上限：

- 有失败 `instrCnt`：`-I` 至少设为 `instrCnt + 10000`。
- 只有 cycle：`-C` 设为 `cycle + 10000`，不设置 `-I`。
- `assertion` 缺少指令数：使用 `error_instrCnt=40000000`，并将 `-I` 设为 `40000000`。

如果最多 5 个候选都不能复现：

- 记录 `无可复现代表 checkpoint`，保留全部候选日志，不生成或伪造代表波形。
- 类别目录仍只保留一个；README、`bug-analysis.md` 和汇总报告链接全部候选证据。
- 继续根据原始日志、候选日志和 `XiangShan-original/` 源码分析并修复。
- 修复后验证写入 `after-fix/validation/<checkpoint-slug>/`。

已有 VCD/FST 直接使用当前 Python 环境的 `pywellen` 查询。不保留额外波形 CLI、缓存层、RTL parser 或 bundled runtime。分析方法见 [waveform.md](references/waveform.md)。

## 第四部分：隔离修复并回归

### 修复

1. 按类别数量降序确定优先级；不同类别可使用独立 agent 并行分析。
2. 每类从匹配 `XiangShan-original/` 的 commit 建立私有 `XiangShan/`。不同类别不得共享可变源码树、`build/emu`、生成 RTL 或 DRAMSim3 输出。
3. 从首次错误向前回溯 PC、指令或请求生命周期，对照 Chisel、生成 RTL、波形、反汇编和参考模型。
4. 根因说明必须包含观察事实、被破坏的不变量、推导过程和验证结果。
5. 做能解释首错的最小修改，并重新构建相同配置的 Verilator emu。
6. 保存 `build-log/build-fixed.log`、基于原始 commit 的 `patch/patch.diff`、普通文件形式的 `after-fix/new-emu` 和修复后日志。修复后产物不得写入 `reproduction/`。

### 有最终代表时回归

1. 先运行 `after-fix/representative/`。上限使用原失败 `instrCnt + 10000`；缺少位置字段的 `assertion` 使用 `40000000 + 10000`，并记录默认回退值。
2. 代表点越过原失败位置，且没有原错误或新功能错误，才进入追加回归。
3. 代表点失败时停止追加回归，状态写为 `未执行（代表点失败）`。
4. 同类总数不超过 5 时运行其余全部 checkpoint；超过 5 时从其余 checkpoint 随机选择最多 4 个，与代表点合计最多 5 个。
5. 固定并记录随机种子、候选集合、实际选择和逐项结果。追加结果写入 `after-fix/additional/<checkpoint-slug>/`。

### 无可复现代表时回归

- 使用 `after-fix/new-emu` 逐个验证已尝试的最多 5 个候选。
- 结果写入 `after-fix/validation/<checkpoint-slug>/`。
- 状态写为 `无可复现代表，基于日志和源码完成回归验证`；不能把任何候选称为代表回归。

修复后遇到另一个已分类错误时，说明它所属的独立类别，不能误报为完整应用通过。逐类完成修复和验证，或明确记录阻塞项。

## 交付

任务根目录必须包含：

- `report-bug-analysis.md`：逐类记录分类、最终代表或无代表状态、首错、根因和现场链接。
- `report-fixed-analysis.md`：按同样类别逐项记录 patch 路径、修复方法、修复后 emu/日志和回归状态。
- `XiangShan-original/`、`cases/` 和各类别的完整证据目录。

每个类别还必须：

- 更新 `README.md`，概述出错场景、修复方法、代表点或 validation 状态、追加回归状态和文件组织。
- 保存 `bug-analysis.md`、`checkpoints.txt`、`build-log/`、`original/`、`reproduction/`、私有 `XiangShan/`、`patch/` 和 `after-fix/` 中实际存在的证据。
- 为 code owner 提供建议的 Git commit title 和 message；message 同时说明失败场景和修复方法。

两个汇总报告必须覆盖全部错误类型，包括未修复或证据不足的类别。有最终代表时，状态只能写为 `通过`、`失败`、`未完成` 或 `缺少证据`；无代表时使用规定的 validation 状态。所有状态都必须链接实际产物。

详细目录树、文件内容和报告表格见 [reproduction-delivery.md](references/reproduction-delivery.md)。

## 操作边界

- 初始构建完成后冻结 `XiangShan-original/`；后续修复只在类别私有 `XiangShan/` 中进行。
- Python 使用当前项目或用户配置的环境，不在 skill 中假设固定虚拟环境路径。
- 默认不执行 `git commit`，绝不执行 `git push`。
- 清理前确认不会删除用户改动、唯一波形或失败现场。
- PR、trigger 和 Actions 产物关联见 [github-actions.md](references/github-actions.md)。
- PC 与 ELF 映射见 [disassembly.md](references/disassembly.md)。
