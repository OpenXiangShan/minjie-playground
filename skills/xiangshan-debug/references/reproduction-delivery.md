# 复现与修复产物契约

本文件只定义任务产物的目录和内容。任务顺序、分类方法、代表 checkpoint 选择、构建参数、复现方式和通过标准以 [SKILL.md](../SKILL.md) 为准。

## 1. 任务级文件

- `plan.md`：记录输入范围、任务拆解、并发安排和验收项。
- `execution.md`：记录源码与配置分组、关键命令、环境、退出码和阶段进度。
- `issues.md`：只记录实际遇到的问题、诊断过程和处理结果。
- `report-bug-analysis.md`：按错误类型汇总分类、代表现场、首错和根因分析，链接逐类证据，不复制完整日志或调试过程。
- `report-fixed-analysis.md`：按同样的错误类型汇总修复 patch 文件概览、修复方法和修复后回归状态，逐类链接 patch、after-fix 和验证日志。
- `XiangShan-original/`：与 `cases/` 同级的任务级共享初始源码，用于第一部分的调试 emu 和所有复现候选；成功复现的候选才成为最终代表。

## 2. `bug-analysis.md`

每个 `bug-analysis.md` 至少记录：

- 类别名称、粗分类、微架构归属、成员数量和输入版本/配置组；同一主错误类型无论来自多少测试输入、版本或配置，都只对应一个 `bug-analysis.md`；
- 预选候选、最终代表 checkpoint（若有）、选择依据、首错签名、PC、cycle 和 `instrCnt`；
- 初始 Verilator 复现候选的尝试顺序、每个候选的退出结果，以及最终代表；如果最多 5 个候选都不能复现，明确记录 `无可复现代表 checkpoint`，不能把预选候选冒充代表；
- 如果类别是 `assertion`，还要记录每个成员的原始 assert message、归一化模板，以及 message 合并或拆分的依据；非数字文本不同的 message 不能放入同一类别。
- checkpoint、原日志、ELF、`vmlinux`、NEMU、Verilator debug/new emu 和 `build-log/` 的路径与摘要，缺失项显式标记；已有 old-emu 只记录其输入来源，不要求生成或运行；
- 复现命令、关键环境、真实退出码、波形路径和复现结论；
- 观察事实、根因假设、验证证据、替代解释和最终根因；
- patch 基准 commit、修复后 emu 配置、本类验证结果、后续错误和额外回归结果。

大段日志、波形查询结果和通用执行记录保存在原始文件或任务 `execution.md`，不要粘贴进 `bug-analysis.md`。

## 3. 类别目录 `README.md`

每个 `cases/<failure-type>-<count>-<test-case>-<checkpoint>/` 必须包含一个 `README.md`，作为 code owner review 的快速入口。README 是摘要文件，不替代 `bug-analysis.md` 的详细根因推理，也不复制完整日志；所有链接使用相对路径并指向该类别目录中的实际产物。

README 至少包含以下三部分：

```markdown
# <failure-type> 场景概览

## 出错场景

- 错误类型、测试用例、同类 checkpoint 总数。
- 预选候选或最终代表 checkpoint（若有）、选择依据、首错签名、`error_instrCnt` 和 `error_cycle`。
- 微架构归属、复现状态，以及 assertion 使用默认 `40000000` 时的说明。
- 如果是 assertion，列出原始 message、归一化模板和该模板为何与其他 message 合并或拆分。
- 如果没有可复现代表，说明 AI 如何根据原始日志、候选日志和 `XiangShan-original` 源码完成分析，以及修复后 `after-fix/validation/` 的回归结论。

## 修复方法

- 根因和修复动作的简要说明，指出受影响模块和恢复的不变量。
- [`patch/patch.diff`](patch/patch.diff) 和 [`patch/message.txt`](patch/message.txt)。
- 修复后 Verilator emu、代表 checkpoint 回归状态，以及追加回归选择和状态。

## 目录文件组织

- [`README.md`](README.md)：本快速概览，供 code owner review。
- [`bug-analysis.md`](bug-analysis.md)：该错误类别的完整原因分析和证据索引。
- [`checkpoints.txt`](checkpoints.txt)：该类全部 checkpoint 的名称、出错节点指令数、周期数和路径。
- `../../XiangShan-original/`：任务级共享初始源码；代表 checkpoint 的调试 emu、波形和复现日志来自该版本。
- `XiangShan/`：该类别独立的私有修复源码，仅用于 patch 和 fixed emu。
- `build-log/`：构建 stdout/stderr；包含 `build-debug.log` 和 `build-fixed.log`。
- `original/`：代表出错场景的原始日志，以及输入已提供的 `old-emu`。
  - `simulator_out.txt`、`simulator_err.txt`：原始运行日志。
  - `old-emu`：仅当输入已提供时保存来源，不由本技能生成。
- `reproduction/`：只使用从 `../../XiangShan-original/` 构建的初始版本带波形 Verilator emu 复现候选 checkpoint。
  - `simulator_out.txt`、`simulator_err.txt`：最终代表候选的复现日志；只有候选成功复现时才生成。
  - `debug-emu`：带波形的 Verilator emu。
  - `wave.fst` 或 `wave.vcd`：最终代表候选的波形；无候选复现时不生成。
  - `candidates/<checkpoint-slug>/`：每个候选的 `simulator_out.txt`、`simulator_err.txt` 和 `exit-code`。
  - `analysis/`：使用当前 Python 环境中的 `pywellen` 直接读取已有 VCD/FST 的信号清单、窗口变化和单点查询结果；不在此目录生成波形。
- `patch/`：修复 patch 和建议的 commit message。
- `after-fix/`：修复后回归；先看 `representative/`，再看 `additional/<checkpoint-slug>/`。
  - `new-emu`：修复后的 Verilator emu。
  - `representative/`：代表 checkpoint 的 `simulator_out.txt`、`simulator_err.txt` 和 `exit-code`。
  - `additional/<checkpoint-slug>/`：追加 checkpoint 的 `simulator_out.txt`、`simulator_err.txt` 和 `exit-code`。
  - `validation/<checkpoint-slug>/`：初始 emu 无候选复现时，修复后基于日志和源码选择的回归验证目标及其 `simulator_out.txt`、`simulator_err.txt` 和 `exit-code`。
```

README 必须在分类、修复和回归完成后更新，状态只能引用实际证据；缺失文件或未执行回归要明确标注，不能用“已完成”等笼统描述代替。

## 4. `checkpoints.txt`

`checkpoints.txt` 是 UTF-8 文本文件，允许注释行；注释行以 `#` 开头，数据行必须使用 TAB 分隔，不能用空格替代。每行记录一个同类 checkpoint，且只记录以下四项直接定位信息：出错 checkpoint 名称、出错节点的指令数、出错节点的周期数和 checkpoint 路径。字段顺序固定如下：

```text
# 1 checkpoint_name: checkpoint 的原始名称或稳定 slug。
# 2 error_instrCnt: 原始日志出错节点对应的提交指令数（instrCnt）；assertion 日志没有该值时固定写 40000000，并在 bug-analysis.md 标明这是默认回退值。
# 3 error_cycle: 原始日志出错节点对应的仿真周期数（cycle）；没有该值写 unknown。assertion 的默认指令数不推导周期数。
# 4 checkpoint_path: checkpoint 文件或目录的绝对路径。
# 不要根据 cycle 和 instrCnt 互相换算；字段内不能出现 TAB；未知值统一写 unknown。40000000 不是日志观测值时必须注明来源。
checkpoint_name<TAB>error_instrCnt<TAB>error_cycle<TAB>checkpoint_path
# 示例：
# gcc-6e5a8c<TAB>1415649<TAB>995162<TAB>/abs/checkpoints/gcc-6e5a8c
# assertion-no-location<TAB>40000000<TAB>unknown<TAB>/abs/checkpoints/assertion-no-location
```

文件必须保留表头注释和字段说明；不能省略整行或只保留代表 checkpoint。代表 checkpoint 在 `bug-analysis.md` 中另行标注，不能通过删除其他成员行来表达。

原始 stdout/stderr、日志路径、测试输入分组、XiangShan commit 和配置等扩展证据记录在 `bug-analysis.md`，不再混入上述四列；这样打开 `checkpoints.txt` 时，每个数据行都能直接读出 checkpoint 和两个出错位置指标。

## 5. 建立逐类交付目录

每轮任务使用新的 `tasks/<YYYYMMDD>-<topic>/`。先跨所有输入按主错误类型合并成员，再为每种错误只建立一个稳定、可读的英文 slug 目录。目录名初始采用预选候选的 `<failure-type>-<count>-<test-case>-<checkpoint>`：`count` 是该错误类型的全部 checkpoint 数量，`test-case` 是预选候选所属的测试用例标签，`checkpoint` 是预选候选名称。如果其他候选成功复现，只允许将这一个类别目录重命名一次，使其匹配最终代表；如果最多 5 个候选都失败，保留预选候选目录名并在 `bug-analysis.md` 标注无可复现代表。四个标签均转为小写英文 slug，只保留字母、数字和单个短横线；目录名冲突时在 `bug-analysis.md` 记录完整原始名称和消歧原因，不得为同类错误再建第二个类别目录。

```text
tasks/<task>/
  plan.md
  execution.md
  issues.md
  report-bug-analysis.md # 对错误类型和首错原因进行概括分析
  report-fixed-analysis.md # 对每类修复 patch 和回归结果进行概览
  XiangShan-original/ # 所有错误类别共享的初始香山源码
  cases/
    <failure-type>-<count>-<test-case>-<checkpoint>/
      README.md # 供 code owner 快速了解出错场景、修复方法和文件组织
      bug-analysis.md # 对这个出错类别的出错原因的记录分析
      checkpoints.txt # 记录该类全部出错检查点的信息，以及对应的路径信息
      XiangShan/  # 该类别私有香山源码，供修复和回归
      build-log/ # 该类别所有编译 stdout/stderr
        build-debug.log # 共享 XiangShan-original 调试 emu 构建日志的现场副本
        build-fixed.log # 修复后 Verilator emu 的构建日志
      original/ # 出错场景的信息记录，包括运行日志和已有旧版emu文件
        simulator_out.txt
        simulator_err.txt
        old-emu # 仅当输入已提供时保存来源，不由本技能生成
      reproduction/ # 使用 XiangShan-original 的 Verilator emu 运行复现候选，成功后保存最终代表日志和波形
        simulator_out.txt
        simulator_err.txt
        debug-emu # 带波形的verilator版emu
        wave.fst or wave.vcd # 波形文件
        candidates/ # 初始 emu 复现候选，最多 5 个
          <checkpoint-slug>/
            simulator_out.txt
            simulator_err.txt
            exit-code
        analysis/ # 使用 pywellen 直接分析已有 VCD/FST 的结果
          signal-list.txt
          changes-<window>.json
          value-<signal>-<time>.json
      patch/ # 代码修复
        patch.diff # 修复的patch，如果改了submodule，如果一个submodule装不下，就需要拆分成多个文件
        message.txt # 为这个修复，写成良好的git commit的title和message
      after-fix/ # 修复后先运行代表点，代表点通过后再运行追加回归点
        new-emu # 修复后的 Verilator emu
        representative/
          simulator_out.txt
          simulator_err.txt
          exit-code
        additional/
          <checkpoint-slug>/
            simulator_out.txt
            simulator_err.txt
            exit-code
        validation/ # 初始 emu 无候选复现时的修复后回归验证
          <checkpoint-slug>/
            simulator_out.txt
            simulator_err.txt
            exit-code
```

## 6. 归档规则

- `original/` 只保存唯一代表现场的原始副本；`reproduction/` 和 `after-fix/` 不能覆盖它。
- 任务级 `XiangShan-original/` 只保留一份初始源码，与 `cases/` 同级；第一部分只从它构建共享调试 emu，不能在类别目录复制另一份初始源码或修改它。
- 类别目录的 `XiangShan/` 必须从 `XiangShan-original/` 对应 commit 独立复制或克隆，仅用于该类别修复；不同类别不得共享可变源码树或生成目录。
- 每个错误类别目录必须有 `README.md`；README 使用相对路径链接实际产物，概述出错场景、修复方法和目录组织，不粘贴完整日志。
- 所有编译 stdout/stderr 必须保存到该类别目录的 `build-log/`；至少使用 `build-debug.log` 和 `build-fixed.log`，多个配置或 submodule 使用带稳定 slug 的附加文件名。不得把编译日志直接放在类别目录、任务根目录或运行结果目录中。
- 输入已提供的 `old-emu` 和本轮生成的初始版本 `debug-emu` 均保存为普通文件，不能使用会被后续构建改写的符号链接；来源与摘要写入 `bug-analysis.md`。不得为了填充 `old-emu` 而生成 gsim，`debug-emu` 必须是来自 `XiangShan-original` 的 Verilator。修复后的 `new-emu` 只能保存在 `after-fix/`。
- checkpoint 镜像只在 `bug-analysis.md` 和 `checkpoints.txt` 记录并验证路径，无需复制大文件。
- 缺失产物写入 `bug-analysis.md` 或 `issues.md`，不得用空文件或相似版本占位。
- `patch.diff` 基于记录的原始 commit 生成；修改多个 Git 仓库或 submodule 时分别保存 patch。
- stdout/stderr 保持原样；摘要、行号和结论写入 Markdown 文档，不能改写日志后再作为原始证据。
- 初始复现从预选候选开始，失败后按记录顺序继续尝试同类 checkpoint，总数最多 5 个；所有尝试日志保存到 `reproduction/candidates/`。第一个复现首错的候选才可提升为 `reproduction/` 根部的最终代表日志和波形。
- 如果全部候选都失败，`reproduction/` 不得生成代表波形；保留候选日志，并将修复后基于日志和源码的回归结果保存到 `after-fix/validation/`。
- 波形分析结果保存到对应类别的 `reproduction/analysis/`；直接调用 `pywellen` 不建立 skill 级查询缓存，也不得写入生产 skill 目录。
- 如果存在最终代表，修复后必须先运行 `after-fix/representative/` 中的唯一代表 checkpoint。代表点失败时停止该类别的追加回归，并记录 `未执行（代表点失败）`；无可复现代表时改用 `after-fix/validation/` 中的候选验证。
- 代表点通过后，若同类 checkpoint 总数不超过 5，运行其余全部 checkpoint；若总数超过 5，从其余 checkpoint 中随机抽取最多 4 个，连同代表点总计最多运行 5 个。固定并记录随机种子、候选集合和实际选择清单，追加结果保存到同一类别目录的 `after-fix/additional/<checkpoint-slug>/`，不得新建第二个类别目录，也不得写入 `reproduction/`。

## 7. `report-bug-analysis.md`

先给出总表：

| 错误类别 | 数量 | 微架构归属 | 最终代表 checkpoint（无则说明） | 首错 | 根因与修复 | 本类验证 | 追加回归摘要 | 现场 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

状态词及其判定以 [SKILL.md](../SKILL.md) 为准。每行链接对应 `README.md`、`bug-analysis.md`、`checkpoints.txt`、候选复现日志、patch 和运行日志；表后只补充跨类别结论、未解决问题和整体风险。最多 5 个候选都不能复现时，代表列填写 `无可复现代表 checkpoint`，并链接 `reproduction/candidates/` 和 `after-fix/validation/`。

## 8. `report-fixed-analysis.md`

该文件是修复 patch 的文件概览，不替代 `bug-analysis.md` 中的详细推理。必须按 `SKILL.md` 的每个错误类型各写一行，不能把多个错误类型合并成一行，也不能遗漏尚未修复或证据不足的类别。

先给出总表：

| 错误类别 | 类别目录 | patch 路径 | 修复方法 | 修复后 emu | 代表回归日志 | 代表 checkpoint 回归状态 | 追加 checkpoint、随机种子与回归状态 | 未解决风险 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

填写要求：

- `patch 路径` 至少链接该类别目录中的 `patch/patch.diff` 和 `patch/message.txt`；没有代码修改时写 `无代码 patch` 并解释原因。
- `修复方法` 用简短文字说明修改的模块、被恢复的不变量和关键行为，不只写“已修复”。
- `修复后 emu` 和 `代表回归日志` 在有最终代表时链接 `after-fix/new-emu`、`after-fix/representative/` 下的 stdout/stderr 和退出码证据；无可复现代表时链接 `after-fix/new-emu` 和 `after-fix/validation/`。
- `代表 checkpoint 回归状态` 在有最终代表时只能根据其实际运行证据填写 `通过`、`失败`、`未完成` 或 `缺少证据`；无可复现代表时填写 `无可复现代表，已完成基于日志和源码的 validation`，并链接每个验证目标。编译成功不能代替运行回归成功。
- 代表点通过后，追加回归列出实际选择的 checkpoint、固定随机种子、候选集合和每个结果；代表点失败时明确写 `未执行（代表点失败）`。追加回归结果链接同一类别目录下的 `after-fix/additional/`，不建立其他类别目录。
