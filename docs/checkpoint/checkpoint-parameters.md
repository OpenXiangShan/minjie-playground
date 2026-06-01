# Checkpoint Parameters

checkpoint 脚本提供 `generate_checkpoint.py` 这一条主入口。

它固定执行四个步骤：
1. `profiling`
2. `cluster`
3. `checkpoint`
4. `metadata`

## 命令行参数

入口：
- `scripts/checkpoint/generate_checkpoint.py`

### `--input-path`

- 必填
- 可以是：
  - 单个 GCPT bin 文件
  - 一个包含多个 GCPT bin 文件的目录
- 如果是目录，脚本会扫描其中所有普通文件

### `--name`

- 仅单文件模式可用
- 用于覆盖自动推导出来的 workload 名
- 目录模式下禁止使用

### `--archive-id`

- 可选
- 指定输出 archive 名
- 如果配合 `--resume-after` 使用，则必须提供

默认命名：
- 单文件模式：`<timestamp>_<workload>`
- 目录模式：`<timestamp>_<input-directory>`

### `output_base`

- 仅 GitHub Action 输入提供
- 可选
- 指定 CI 输出根目录
- 默认值是 `/nfs/home/share/<runner-username>/checkpoint-trigger`

### `nemu`

- 仅 GitHub Action 输入提供
- 可选
- 默认值是 `riscv64-xs-cpt_defconfig`
- 以 `_defconfig` 结尾时，会在 CI workspace 拉取 upstream NEMU，并编译 NEMU、`gcpt_restore` 和 `simpoint`
- 否则会当作现有 NEMU 路径，并检查以下文件都存在且可执行：
  - `build/riscv64-nemu-interpreter`
  - `resource/simpoint/simpoint_repo/bin/simpoint`

### `--interval`

- 可选
- 默认 `20000000`
- 必须是正整数
- 会同时传给 profiling 和 checkpoint 阶段

### `--max-k`

- 可选
- 用于覆盖 SimPoint 聚类时的 `-maxK`
- 必须是正整数
- 实际生效值是 `max(内置 workload 默认值, 用户输入值)`
- 当前内置特例：
  - `xalancbmk` 最低为 `100`
  - 其它 workload 最低为 `30`

### `--max-workers`

- 可选
- 默认 `3`
- 只在目录模式下有意义
- 表示同时并行多少个 workload

### `--resume-after`

- 可选
- 允许值：
  - `profiling`
  - `cluster`
  - `auto`

语义：
- `profiling`
  跳过 profiling，直接从 cluster 开始
- `cluster`
  跳过 profiling 和 cluster，直接重新生成 checkpoint
- `auto`
  自动根据 archive 中已有产物判断应该从哪一步继续

## 自动命名

如果没有显式传 `--name`，脚本会自动从文件名推导 workload 名。

当前优先识别的后缀是：
- `.fw_payload.bin`
- `.bin`

示例：
- `gcc_expr.fw_payload.bin` -> `gcc_expr`
- `bwaves.bin` -> `bwaves`

目录模式下，会先尝试找所有文件的公共后缀，再据此批量推导 workload 名。

## 环境要求

必须设置：
- `NEMU_HOME`

必须存在：
- `$NEMU_HOME/build/riscv64-nemu-interpreter`
- `$NEMU_HOME/resource/simpoint/simpoint_repo/bin/simpoint`

## 输出目录

本地直接运行脚本时，默认会写到：
- `archive/<archive-id>/`

GitHub Action 默认会写到：
- `/nfs/home/share/<runner-username>/checkpoint-trigger/<archive-id>/`

如果 workflow 里显式传了 `output_base`，则会写到：
- `<output_base>/<archive-id>/`

archive 顶层固定包含：
- `profiling/`
- `cluster/`
- `checkpoint/`
- `logs/`
- `metadata/`
- `json/`

其中：
- `json/checkpoints_all.json`
- `json/checkpoints_cov0.3.json`
- `checkpoint/checkpoint.lst`

会在 metadata 阶段统一生成。
