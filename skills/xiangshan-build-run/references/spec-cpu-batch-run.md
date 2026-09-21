# SPECCPU 检查点批量运行参考

## 目录

- [原则与依赖发现](#原则与依赖发现)
- [确认运行配置](#确认运行配置)
- [解析检查点配置](#解析检查点配置)
- [准备输出和编译 emu](#准备输出和编译-emu)
- [运行与监控](#运行与监控)
- [生成分数和失败列表](#生成分数和失败列表)
- [中断恢复与边界](#中断恢复与边界)

## 原则与依赖发现

优先使用 XiangShan 项目当前 CI 采用的批量调度工具，不要手写循环直接启动大量 emu。成熟的调度工具通常负责服务器选择、空闲核心分配、NUMA 绑定、检查点状态识别、同一结果目录锁、断点复用、日志归档、加权算分和失败检查点汇总；这些能力是简单循环不具备的。

不要假定 `perf_trigger`、Python 环境、检查点或其他依赖位于某个固定的用户目录或共享文件系统。按以下顺序发现依赖：

1. 读取目标仓库当前的 `.github/workflows/perf-trigger.yml`、`.github/workflows/perf-template.yml` 及相关项目文档。
2. 确认 workflow 使用的批量调度入口。它可能位于目标仓库、单独的工具仓库、容器或站点共享目录。
3. 按项目文档选择 Python 解释器和依赖环境，例如已激活的 venv/Conda 环境、`uv`、容器或系统 Python。不要假定环境名称和激活脚本路径。
4. 如果 workflow 引用当前机器不可访问的内部路径，停止并请用户提供本环境可用的工具、检查点和依赖路径；不要照抄其他部署的绝对路径。

下面的变量必须解析成当前环境中的值：

```bash
export NOOP_HOME=/absolute/path/to/XiangShan
PERF_TRIGGER_DIR=/absolute/path/to/perf_trigger
PYTHON_BIN=${PYTHON_BIN:-python3}
test -d "$NOOP_HOME" || exit 1
test -f "$PERF_TRIGGER_DIR/main.py" || exit 1
"$PYTHON_BIN" "$PERF_TRIGGER_DIR/main.py" --help
```

如果当前项目要求先激活 Python 环境，应在运行上述命令前按项目文档完成激活；技能不规定具体激活命令。若缺少依赖，先检查工具的 `requirements.txt`、`pyproject.toml` 或安装文档，获得用户许可后再修改环境。

## 确认运行配置

只有用户明确要求批量运行并确认配置后才开始。逐项记录：

| 配置 | 必须明确的内容 |
| --- | --- |
| 源码 | `NOOP_HOME`、commit、工作区修改是否保留 |
| Python | 项目要求的环境以及实际 Python 调用方式 |
| 调度工具 | `PERF_TRIGGER_DIR`、版本或 commit、当前 `--help` 接口 |
| 核配置 | 当前构建脚本支持且用户选择的 XiangShan config |
| 检查点 | SPEC 版本、编译器/ISA 版本、0.3/0.8/1.0 覆盖、`CKPT_HOME` 与 `CKPT_JSON_PATH` |
| 模拟器 | `gsim` 或 `verilator` |
| 调度范围 | 当前工具支持且用户确认的服务器或执行资源列表 |
| benchmark | 全部或当前工具支持的过滤表达式 |
| 指令窗口 | `WARMUP_INSTS`、`TOTAL_INSTS`，取自当前 workflow、工具默认值或用户要求 |
| 报告频率 | `FREQUENCY_GHZ`，取自当前 workflow 或用户要求 |
| 外部依赖 | `DRAMSIM3_HOME`、`LLVM_PROFDATA_BIN`、`BUILD_JOBS` 及其他构建工具 |
| 可选功能 | Constantin 文件、ChiselDB、rolling DB；未明确要求时关闭 |
| 输出 | 用户指定根目录，或 XiangShan 仓库的兄弟目录 |

选择规则：

- `gsim` emu 使用 1 个线程，适合更高并行度和 1.0 全覆盖。
- `verilator` emu 使用 8 个线程，并行度较低，默认建议 0.3 覆盖；只有资源和时间足够且用户确认后才运行 1.0。
- 0.3、0.8、1.0 表示 JSON 选取的检查点覆盖范围。覆盖越高，检查点越多、时间越长；实际覆盖率以报告为准，不根据文件名假定恰好等于标称值。
- 不假定任何服务器别名在不同部署中含义相同。使用 `--help`、工具配置或源码确认服务器参数；空值只有在用户接受工具默认策略时才使用。
- ChiselDB 可能为每个检查点产生数 GiB 数据。只有用户明确要求并确认磁盘容量后才启用；rolling DB 通常隐含启用 DB，但仍以当前构建脚本为准。

## 解析检查点配置

不要在公开技能中维护某个站点的检查点绝对路径。对用户选择的 `benchmark_type`，从当前 workflow 的同一个分支同时解析 `CKPT_HOME` 和 `CKPT_JSON_PATH`：

```bash
WORKFLOW_DIR="$NOOP_HOME/.github/workflows"
test -d "$WORKFLOW_DIR" || exit 1
rg -n 'benchmark_type|CKPT_HOME|CKPT_JSON_PATH|perf_trigger|SCRIPTS_HOME' \
  "$WORKFLOW_DIR"
```

如果当前环境没有 `rg`，使用可用的等价文本搜索工具。解析时遵守以下规则：

- `*-0.3c` 选择当前检查点版本对应的约 0.3 覆盖 JSON。
- `*-0.8c` 选择当前检查点版本对应的约 0.8 覆盖 JSON。
- `*-1.0c` 选择当前检查点版本的全量 JSON。
- `custom` 必须由用户同时提供检查点目录和 JSON。
- workflow 没有该 `benchmark_type`、路径不存在或目录与 JSON 版本不匹配时立即停止。
- 不要把名称相近但版本、ISA、编译器或生成日期不同的目录和 JSON 拼接使用。

如果目标仓库没有这些 workflow，要求用户提供 `PERF_TRIGGER_DIR`、`CKPT_HOME` 和 `CKPT_JSON_PATH`，并用调度工具的文档或 `--help` 验证。配置完成后执行：

```bash
CKPT_HOME=/absolute/path/to/checkpoints
CKPT_JSON_PATH=/absolute/path/to/checkpoints.json
test -d "$CKPT_HOME" || exit 1
test -f "$CKPT_JSON_PATH" || exit 1
```

## 准备输出和编译 emu

使用已经确认的 `benchmark_type` 创建唯一结果目录：

```bash
export NOOP_HOME=/absolute/path/to/XiangShan
BENCHMARK_TYPE=selected-benchmark-type
SPEC_EDITION="$BENCHMARK_TYPE"
DATE=$(date +%Y%m%d-%H%M%S)
XS_COMMIT_ID=$(git -C "$NOOP_HOME" rev-parse --short=9 HEAD)
RESULT_ROOT=${RESULT_ROOT:-$(dirname "$NOOP_HOME")}
EMU_TASK_DIR="$RESULT_ROOT/XiangShan-EmuTask-${DATE}-${XS_COMMIT_ID}-${SPEC_EDITION}"
test -d "$NOOP_HOME" || exit 1
test ! -e "$EMU_TASK_DIR" || exit 1
mkdir -p "$EMU_TASK_DIR"
```

唯一目录用于冻结本次 emu、NEMU 和配置，避免并发任务混用日志或二进制。创建后记录 commit、`git status --short`、全部配置和实际命令。

按目标仓库当前 workflow 和 `scripts/xiangshan.py --help` 构建。下面给出参数结构，不提供站点路径；`EMU_THREADS` 必须与运行阶段一致：

```bash
export NOOP_HOME=/absolute/path/to/XiangShan
PYTHON_BIN=${PYTHON_BIN:-python3}
DRAMSIM3_HOME=/absolute/path/to/DRAMSim3
LLVM_PROFDATA_BIN=${LLVM_PROFDATA_BIN:-llvm-profdata}
: "${BUILD_JOBS:?Set BUILD_JOBS for this host}"
cd "$NOOP_HOME" || exit 1
EMULATOR=gsim
EMU_THREADS=1
XS_CONFIG=SelectedConfig
test -d "$DRAMSIM3_HOME" || exit 1
BUILD_ARGS=(
  --build
  --config "$XS_CONFIG"
  --dramsim3 "$DRAMSIM3_HOME"
  --with-dramsim3
  --threads "$EMU_THREADS"
  --make-threads "$BUILD_JOBS"
  --pgo "$NOOP_HOME/ready-to-run/coremark-2-iteration.bin"
  --llvm-profdata "$LLVM_PROFDATA_BIN"
  --trace-fst
  --emulator "$EMULATOR"
)
[[ -n ${CST_FILE:-} ]] && BUILD_ARGS+=(--with-constantin)
[[ ${ENABLE_DB:-false} == true ]] && BUILD_ARGS+=(--enable-db)
[[ ${ENABLE_ROLLING:-false} == true ]] && BUILD_ARGS+=(--enable-rolling)
"$PYTHON_BIN" scripts/xiangshan.py "${BUILD_ARGS[@]}" || exit 1
test -x "$NOOP_HOME/build/emu" || exit 1
test -f "$NOOP_HOME/ready-to-run/riscv64-nemu-interpreter-so" || exit 1
cp "$NOOP_HOME/build/emu" "$EMU_TASK_DIR/emu-$EMULATOR"
cp "$NOOP_HOME/ready-to-run/riscv64-nemu-interpreter-so" \
  "$EMU_TASK_DIR/riscv64-nemu-interpreter-so"
```

运行 Python 命令前，使用此前确认的项目环境。不要无条件执行 `--clean`。若现有 `build/emu` 的模拟器、线程数、核配置、DRAMSim3、Constantin 或 DB 选项无法确认与本次一致，则重新构建，不能把不明来源的 emu 当成本次产物。

启动前至少检查：

```bash
test -d "$CKPT_HOME" || exit 1
test -f "$CKPT_JSON_PATH" || exit 1
test -f "$PERF_TRIGGER_DIR/main.py" || exit 1
test -x "$EMU_TASK_DIR/emu-$EMULATOR" || exit 1
test -f "$EMU_TASK_DIR/riscv64-nemu-interpreter-so" || exit 1
[[ -z ${CST_FILE:-} || -f "$CST_FILE" ]] || exit 1
df -h "$EMU_TASK_DIR"
"$PYTHON_BIN" "$PERF_TRIGGER_DIR/main.py" --help
```

## 运行与监控

先设置 workflow、工具默认值或用户已经确认的运行参数。`BENCHMARKS` 为空表示全部的前提是当前工具如此定义；`SERVER_LIST` 必须使用当前部署支持的值：

```bash
PYTHON_BIN=${PYTHON_BIN:-python3}
WARMUP_INSTS=20000000
TOTAL_INSTS=40000000
SERVER_LIST=confirmed-server-selection
cd "$PERF_TRIGGER_DIR" || exit 1
RUN_ARGS=(
  --gcpt-path "$CKPT_HOME"
  --json-path "$CKPT_JSON_PATH"
  --emu-path "$EMU_TASK_DIR/emu-$EMULATOR"
  --result-path "$EMU_TASK_DIR"
  --threads "$EMU_THREADS"
  --warmup "$WARMUP_INSTS"
  --max-instr "$TOTAL_INSTS"
  --benchmarks "${BENCHMARKS:-}"
  --server-list "$SERVER_LIST"
  --nemu-so-path "$EMU_TASK_DIR/riscv64-nemu-interpreter-so"
  --run
)
[[ -n ${CST_FILE:-} ]] && RUN_ARGS+=(--cst-file "$CST_FILE")
if [[ ${ENABLE_DB:-false} == true || ${ENABLE_ROLLING:-false} == true ]]; then
  RUN_ARGS+=(--dump-db)
fi
"$PYTHON_BIN" main.py "${RUN_ARGS[@]}"
RUN_STATUS=$?
printf '%s\n' "$RUN_STATUS" >"$EMU_TASK_DIR/runner.exit-code"
```

示例中的指令数只反映一种常见配置，执行时必须以当前 workflow、`--help` 或用户确认值为准。

运行可能超过 24 小时。将已经展开为绝对路径、并包含正确 Python 调用方式的命令保存为 `$EMU_TASK_DIR/run-spec.sh`，再使用当前平台可恢复的持久执行机制启动，例如终端复用器、作业调度器、服务管理器或容器任务。不要假定某一种机制已经安装，不要依赖会随交互终端断开而终止的前台 shell，也不要设置 24 小时以内的超时。记录任务标识，并定期检查：

```bash
tail -n 80 "$EMU_TASK_DIR"/runner_*.log
find "$EMU_TASK_DIR" -name simulator_out.txt -type f | wc -l
find "$EMU_TASK_DIR" -name simulator_err.txt -type f | wc -l
test -f "$EMU_TASK_DIR/runner.exit-code" && cat "$EMU_TASK_DIR/runner.exit-code"
```

不要只根据 emu 日志文件数量判断完成。以启动进程结束、`runner.exit-code` 生成和报告汇总三者共同判断。运行脚本应将每个检查点的 stdout/stderr 放在独立目录，并在调度日志中周期性报告已分配、已完成和剩余检查点。

## 生成分数和失败列表

等待批量运行进程结束后，使用完全相同的检查点目录、JSON、结果目录和 benchmark 过滤条件：

```bash
PYTHON_BIN=${PYTHON_BIN:-python3}
FREQUENCY_GHZ=3.0
cd "$PERF_TRIGGER_DIR" || exit 1
SCORE_FILE="$EMU_TASK_DIR/score-${BENCHMARK_TYPE}.txt"
"$PYTHON_BIN" main.py \
  --gcpt-path "$CKPT_HOME" \
  --json-path "$CKPT_JSON_PATH" \
  --result-path "$EMU_TASK_DIR" \
  --benchmarks "${BENCHMARKS:-}" \
  --frequency "$FREQUENCY_GHZ" \
  --report \
  >"$SCORE_FILE"
REPORT_STATUS=$?
printf '%s\n' "$REPORT_STATUS" >"$EMU_TASK_DIR/report.exit-code"
```

示例频率只用于说明参数形式，执行时使用当前 workflow 或用户确认值。报告通常包含各 benchmark 分数、int/fp/total 每 GHz 汇总、目标频率分数、最小覆盖率、成功检查点数量和失败检查点列表；以当前工具实际输出为准。初步汇报至少给出：

- `runner.exit-code` 与 `report.exit-code`。
- `SCORE_FILE` 和结果目录绝对路径。
- SPEC int、fp、total 分数及报告使用的频率。
- 覆盖率与成功/总检查点数量。
- 失败检查点完整列表；为空时明确写无失败项。

调度工具发现单个检查点失败时，整个进程仍可能返回 0。因此退出码为 0 不代表所有检查点成功，必须读取报告中的完成数量和失败列表。有失败或覆盖不足时，将分数标为部分结果，不做深入原因分析。

## 中断恢复与边界

- 不要在相同结果目录并发启动两个运行任务；先确认原进程和持久任务状态。
- 确认原进程已经停止后，查阅当前调度工具的恢复语义，再决定是否对同一结果目录重跑。只有工具明确支持时，才依赖已完成项跳过和遗留运行项重调度。
- 清理或重置运行状态可能删除输出文件。只有确认没有活跃任务且用户同意后才执行。
- 不要自动把失效路径替换为名称相近的检查点版本；目录、JSON 和 profile 必须属于同一版本。
- 本技能只生成基础 score 和失败列表。跨版本加权比较、IPC/TopDown/性能计数器分析使用相应性能分析工具或 SKILL；失败根因和波形分析使用调试工具或 SKILL。
