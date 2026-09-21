---
name: xiangshan-build-run
description: 当需要从 GitHub 克隆或检出 XiangShan 源码、初始化子模块、使用 gsim 或 Verilator 编译 emu、运行用户指定或当前环境可用的工作负载时使用；也用于用户明确要求批量运行 SPECCPU 检查点并已确认本地配置后，执行大规模并行运行、生成基础分数和失败检查点列表。仅负责源码准备、编译、运行和批量结果初筛，不负责性能计数器、波形或源码问题的深入分析。
---

# XiangShan 编译与运行

本 SKILL 负责准备源码、编译和运行。普通负载运行后记录退出码及日志路径；SPECCPU 批量任务额外生成分数与失败检查点列表。性能计数器、波形或源码问题的深入分析交由其他 SKILL。

## 1. 获取并初始化源码

优先使用任务指定的香山仓库。需要克隆时，先确认目标路径不包含需要保留的文件；若运行环境需要网络代理，使用用户或平台已经配置的代理方式，不假定存在特定命令、alias 或代理地址。克隆后将 `NOOP_HOME` 设为仓库绝对路径。若任务指定 commit，先检出该 commit，再初始化对应版本的子模块：

```bash
XS_DIR=/absolute/path/to/XiangShan
git clone https://github.com/OpenXiangShan/XiangShan.git "$XS_DIR"
export NOOP_HOME="$XS_DIR"
cd "$NOOP_HOME"
if [[ -n ${XS_COMMIT:-} ]]; then
  git checkout --detach "$XS_COMMIT"
fi
make init
```

未指定 commit 时跳过 `git checkout`。若指定的 commit 尚未下载，先用 `git fetch origin "$XS_COMMIT"` 获取，再检出。对于已有仓库，不重复克隆；检查其版本及工作区状态，保留现有修改，需要下载子模块时在仓库根目录运行 `make init`。不要提交或推送。

## 2. 编译 emu

编译前始终将 `NOOP_HOME` 设为本次香山仓库根目录，并确认目录存在。在该仓库执行：

根据构建主机可用 CPU 和并发策略设置 `BUILD_JOBS`，不要硬编码某台机器的并行度：

```bash
export NOOP_HOME=/absolute/path/to/XiangShan
: "${BUILD_JOBS:?Set BUILD_JOBS for this host}"
test -d "$NOOP_HOME" || exit 1
cd "$NOOP_HOME"
make emu EMU_THREADS=8 EMU_TRACE=1 WITH_DRAMSIM3=1 -j"$BUILD_JOBS" || exit 1
test -x "$NOOP_HOME/build/emu" || exit 1
```

- `EMU_THREADS=8`：emu 使用 8 线程运行。
- `EMU_TRACE=1`：允许 emu 生成波形。
- `WITH_DRAMSIM3=1`：使用 DRAMSim3 模拟 DDR。
- `NUM_CORES=1`：单核默认值；仅在需要多核时显式设置其他值。

当需要运行 emu 且 `build/emu` 不存在或者修改了代码时，需要重新构建；构建依次经历 Chisel 生成 Verilog、Verilator 将 Verilog 转换为 C++、C++ 编译生成 `build/emu`。后两阶段可能较慢，耗时取决于主机配置和并行度，不要只凭耗时判断失败。不要无条件执行 `make clean` 或重复构建；构建失败时不要把旧的 `build/emu` 当作本次构建结果。

## 3. 选择并运行工作负载

任务提供负载时运行指定负载；复现运行失败时优先运行出错负载，数量较多则选代表性负载。未提供负载时，从目标仓库文档、CI 配置或用户环境中查找可用的 smoke workload，并让用户确认；F16 与 Linux 启动镜像是常见选择，但其路径依赖部署环境，不能硬编码。找不到可用负载时停止并请用户提供。

运行前设置 `NOOP_HOME` 并检查 `build/emu`、负载和 difftest 文件。单核使用 `$NOOP_HOME/ready-to-run/riscv64-nemu-interpreter-so`；多核使用 `$NOOP_HOME/ready-to-run/riscv64-nemu-interpreter-dual-so`。为每次运行准备独立的 `RUN_DIR`，分别保存 stdout 和 stderr：

```bash
export NOOP_HOME=/absolute/path/to/XiangShan
WORKLOAD=/absolute/path/to/workload
NEMU_SO="$NOOP_HOME/ready-to-run/riscv64-nemu-interpreter-so"
RUN_DIR=/absolute/path/to/run-output
test -x "$NOOP_HOME/build/emu" || exit 1
test -f "$WORKLOAD" || exit 1
test -f "$NEMU_SO" || exit 1
mkdir -p "$RUN_DIR"
EMU_LIMITS=()
if [[ -n ${WARMUP_INSTS:-} ]]; then
  EMU_LIMITS+=(-W "$WARMUP_INSTS")
fi
if [[ -n ${TOTAL_INSTS:-} ]]; then
  EMU_LIMITS+=(-I "$TOTAL_INSTS")
fi

"$NOOP_HOME/build/emu" -i "$WORKLOAD" --diff "$NEMU_SO" \
  "${EMU_LIMITS[@]}" --enable-fork \
  >"$RUN_DIR/simulator_out.txt" 2>"$RUN_DIR/simulator_err.txt"
EMU_STATUS=$?
printf '%s\n' "$EMU_STATUS" >"$RUN_DIR/exit-code"
```

按任务设置 `WARMUP_INSTS` 和 `TOTAL_INSTS`；设定后命令分别添加 `-W "$WARMUP_INSTS"` 和 `-I "$TOTAL_INSTS"`。未设定时不传入这些参数。普通 smoke workload 通常等待程序自行结束，除非用户或项目测试配置给出上限。

参数含义：

- `-i` 指定输入负载；`--diff` 指定作为正确性对照的 NEMU 共享库。
- `-W` 指定预热指令数；达到后输出一次性能计数器并清零，仅影响计数器，不影响功能正确性。
- `-I` 限制 emu 执行的总指令数；`-C` 可选，用于限制 emu 总周期数。二者与主机指令数、运行时间无关；未指定时对应上限为无限。
- `--enable-fork` 开启 LightSSS：运行时定期 fork，出错时从最老的 fork 进程重放并开启波形。

`simulator_out.txt` 保存运行日志：`HIT GOOD TRAP` 表示程序正确结束，`EXCEEDING CYCLE/INSTR LIMIT` 表示达到设定上限，`HIT BAD TRAP` 表示运行失败并包含现场信息。assert 失败可能没有 `HIT BAD TRAP`，应查看 assert 信息。`simulator_err.txt` 主要是大量性能计数器输出，assert 信息也可能在其中。只做基本状态核对并报告退出码及日志位置；其他失败类型和性能计数器的深入分析不属于本 SKILL。

## 4. 批量运行 SPECCPU 检查点

只有用户主动明确要求在本地运行 SPECCPU 检查点，并且已经给出或确认以下配置后，才能启动批量任务：目标仓库与 commit、`xs_config`、检查点版本和权重覆盖、`gsim` 或 `verilator`、服务器范围、全部或指定 benchmark，以及 Constantin/ChiselDB 等可选项。信息不完整时先给出建议并等待确认；普通编译、单负载运行、性能分析或 CI 排查请求都不能隐式触发 SPECCPU 批量运行。

执行前必须完整读取 [SPECCPU 批量运行参考](references/spec-cpu-batch-run.md)。优先从目标仓库当前的 workflow、项目文档和工具 `--help` 解析脚本接口及路径；无法访问其中引用的外部工具或数据时，要求用户提供本环境中的等价路径，不能沿用其他部署环境的绝对路径。

按三个阶段执行：

1. 配置与预检查：选择相互匹配的检查点目录和 JSON。`gsim` emu 为单线程，可并行更多实例，优先用于 1.0 覆盖；`verilator` emu 为 8 线程，并行度较低，默认建议 0.3 覆盖。检查路径、磁盘、服务器、emu、NEMU 和脚本接口，任何缺失都先停止。
2. 编译与批量运行：始终设置 `NOOP_HOME`，用目标仓库的 `scripts/xiangshan.py` 按 CI 参数构建对应模拟器，再由 `perf_trigger` 调度检查点。使用独立结果目录；未指定根目录时放在 XiangShan 仓库的兄弟目录，并命名为 `XiangShan-EmuTask-${DATE}-${XS_COMMIT_ID}-${SPEC_EDITION}`。任务可能超过 24 小时，应放入可恢复的持久会话，持续记录状态，不设置短超时，也不启动同一结果目录的并发副本。
3. 初步汇总：运行相同 `gcpt-path`、JSON、结果目录和 benchmark 过滤条件的 `--report`，保存 score 文件，并同时报告 SPECCPU 分数、覆盖率、成功检查点数量和失败检查点列表。即使批量运行进程退出码为 0，也必须检查失败列表；存在失败时不得把部分结果表述为完整有效分数。

只做上述初步汇总。需要比较多个版本、分析 IPC/TopDown/详细计数器时，使用当前环境可用的 XiangShan 性能分析工具或 SKILL；需要分析错误日志或波形时，使用对应的调试工具或 SKILL。
