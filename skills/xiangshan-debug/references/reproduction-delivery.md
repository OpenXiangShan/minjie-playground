# 复现与修复产物契约

本文件只定义一个失败用例任务的目录和内容。任务顺序、错误分类、复现方式、构建参数和通过标准以 [SKILL.md](../SKILL.md) 为准。

## 1. 任务根目录文件

所有产物直接位于当前任务根目录，不创建 `cases/` 或其他类别目录：

- `README.md`：供 code owner 快速了解这个失败、根因、修复和当前回归状态；流程完成后更新。
- `plan.md`：输入范围、执行步骤和验收项。
- `execution.md`：源码与配置、关键命令、环境、退出码和阶段进度。
- `issues.md`：实际遇到的问题、证据缺口、阻塞和处理结果。
- `bug-analysis.md`：这一个失败用例的完整分类、根因推理和证据索引。
- `checkpoints.txt`：这个报错唯一 checkpoint 的定位信息，数据行只能有一条。
- `report-bug-analysis.md`：单个失败用例的首错、根因和复现状态摘要。
- `report-fixed-analysis.md`：单个失败用例的 patch、修复 emu 和回归状态摘要。
- `XiangShan-original/`：manifest 或用户指定现场确认的 commit 的冻结基线源码。
- `XiangShan/`：从同一 commit 派生的唯一可变修复源码。

## 2. 根目录 `README.md`

README 是 code owner 的快速入口，不替代 `bug-analysis.md`，也不复制完整日志。至少包含：

```markdown
# <failure-type> 场景概览

## 当前状态

- workload、checkpoint、报告、branch、XiangShan commit 和首错位置。
- 当前主错误类型、微架构归属、复现状态和证据缺口。

## 根因与修复

- 观察事实、被破坏的不变量、根因结论或待验证假设。
- [`patch/patch.diff`](patch/patch.diff) 和 [`patch/message.txt`](patch/message.txt)。

## 回归

- 初始版本复现、修复后同一 checkpoint 的实际状态，以及触发条件覆盖证据。
- 如果没有可复现代表，明确说明 `after-fix/validation/` 的验证结论和证据缺口。

## 文件组织

- [`bug-analysis.md`](bug-analysis.md)：完整原因分析和证据索引。
- [`checkpoints.txt`](checkpoints.txt)：这个输入的 checkpoint、指令数、周期数和路径。
- [`XiangShan-original/`](XiangShan-original/)：冻结基线源码。
- [`XiangShan/`](XiangShan/)：私有修复源码。
- [`build-log/`](build-log/)：初始和修复构建日志。
- [`original/`](original/)：原始日志和输入已提供的 `old-emu`。
- [`reproduction/`](reproduction/)：初始版本运行日志、波形和 `pywellen` 分析。
- [`patch/`](patch/)：patch 和建议的 commit message。
- [`after-fix/`](after-fix/)：修复后的 emu 和回归结果。
```

缺失文件或未执行回归必须明确写出，不能用“已完成”等笼统描述代替。

## 3. `bug-analysis.md`

至少记录：

- workload、checkpoint、报告名、branch、完整 XiangShan commit 和 manifest 路径；
- 粗分类、微架构归属、首错签名、PC、cycle、`instrCnt`，以及 assertion 的原始 message 和归一化模板；
- 原始日志、checkpoint、ELF、`vmlinux`、NEMU、初始 debug emu 和 fixed emu 的路径与摘要，缺失项显式标记；
- 用户提供 FSDB 时，记录原始波形与日志/RTL 版本的关联，以及导出工具版本、时间窗口、信号/层级选择、转换日志和 FST checksum；
- 复现命令、环境、真实退出码、波形路径和复现结论；
- 观察事实、根因假设、替代解释、最终根因和验证结果；
- patch 基准 commit、修复后 emu 配置、同一 checkpoint 结果和触发条件覆盖结果。

大段日志、波形查询结果和通用执行记录保存在原始文件或 `execution.md`，不要粘贴进分析文档。

## 4. `checkpoints.txt`

文件为 UTF-8 文本，允许以 `#` 开头的注释行；数据行使用 TAB 分隔，固定四列：

```text
# checkpoint_name<TAB>error_instrCnt<TAB>error_cycle<TAB>checkpoint_path
# 日志缺失的指令数或周期数写 unknown；运行预算单独记录在 execution.md。
<name>	<instrCnt-or-unknown>	<cycle-or-unknown>	<absolute-checkpoint-path>
```

不能根据 cycle 和 `instrCnt` 互相换算，也不能删除任务提供的 checkpoint 记录来伪造代表点。

## 5. 目录和运行证据

```text
<task>/
  README.md
  plan.md
  execution.md
  issues.md
  bug-analysis.md
  checkpoints.txt
  report-bug-analysis.md
  report-fixed-analysis.md
  XiangShan-original/
  XiangShan/
  build-log/
    build-debug.log
    build-fixed.log
  original/
    simulator_out.txt
    simulator_err.txt
    old-emu                  # 仅当输入已提供
    analysis/                # 仅当分析用户提供的波形现场
      fsdb-export/           # 已完成的 FSDB 导出及转换记录
        <prefix>.fst
        <prefix>.command.txt
        <prefix>.summary.txt
        <prefix>.fsdb2vcd.log
        <prefix>.vcd2fst.log
        <prefix>.SHA256SUMS
  reproduction/
    simulator_out.txt
    simulator_err.txt
    exit-code
    debug-emu
    wave.fst or wave.vcd
    candidates/              # 仅在确有同一 checkpoint 的有依据重试时创建
      <attempt-slug>/
        simulator_out.txt
        simulator_err.txt
        exit-code
    analysis/
      signal-candidates.txt
      changes-<window>.json
      value-<signal>-<time>.json
  patch/
    patch.diff
    message.txt
  after-fix/
    new-emu
    representative/
      simulator_out.txt
      simulator_err.txt
      exit-code
    validation/<attempt-slug>/
      simulator_out.txt
      simulator_err.txt
      exit-code
```

`old-emu`、`candidates/` 和 `validation/` 是条件目录；没有真实证据时不要创建空目录或占位文件。运行日志、波形和退出码必须来自同一次 invocation；原始日志不能被复现或修复日志覆盖。

## 6. 归档规则

- `XiangShan-original/` 检出已确认的 commit 后冻结；所有初始复现使用这份源码和对应 debug emu。
- `XiangShan/` 只能用于 patch 和 fixed emu；不得修改或复用可变的 `XiangShan-original/`。
- 所有编译 stdout/stderr 放入根目录 `build-log/`，至少有 `build-debug.log` 和 `build-fixed.log`；不能把构建日志写入源代码目录或运行目录。
- 输入已提供的 `old-emu` 和本轮生成的 `debug-emu`、`new-emu` 均保存为普通文件，不能使用会被后续构建改写的符号链接；不得为了填充 `old-emu` 生成 gsim。
- checkpoint 大文件只在 `bug-analysis.md` 和 `checkpoints.txt` 记录、验证和引用，不复制到任务目录。
- `patch.diff` 必须基于记录的原始 commit 生成；主仓和 submodule 有改动时分别保存 patch，并在 `message.txt` 记录应用顺序。
- stdout/stderr 保持原样；摘要、行号和结论写入 Markdown 文档。
- FSDB 原始输入保留现场路径和身份记录；先检查选定转换主机的共享存储访问，仅在不可访问时复制。已有现场的完成导出和转换记录保存在 `original/analysis/fsdb-export/`；远端 scratch 路径写入 `execution.md`，大型中间 VCD 可留在远端。基线或修复运行的转换结果保存在对应运行目录的 `analysis/`，原始现场转换不能记为本轮复现成功。详见 [fsdb-waveform.md](fsdb-waveform.md)。
- 如果初始 emu 无法复现，保留同一 checkpoint 的实际尝试日志，不生成代表波形，并把修复后验证写入 `after-fix/validation/`。
- 修复验证只运行这个 checkpoint；不把其他 workload、checkpoint 或“追加回归”写入本任务。

## 7. 两个报告

`report-bug-analysis.md` 只描述这个失败用例：

```markdown
# Bug Analysis Report

| 项目 | 结果 |
| --- | --- |
| Failure type | ... |
| Workload / checkpoint | ... |
| First error | ... |
| Reproduction | ... |
| Root cause | ... |
| Evidence | [`bug-analysis.md`](bug-analysis.md) |
```

`report-fixed-analysis.md` 只描述这个失败用例：

```markdown
# Fixed Analysis Report

| 项目 | 结果 |
| --- | --- |
| Patch | [`patch/patch.diff`](patch/patch.diff) |
| Fixed emu | [`after-fix/new-emu`](after-fix/new-emu) |
| Representative regression | ... |
| Trigger coverage | ... |
| Remaining risk | ... |
```

状态必须由实际运行证据支持；缺少证据时写 `缺少证据`、`未完成` 或具体 blocker，并链接实际文件。
