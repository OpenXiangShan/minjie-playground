# 命令模板与生成物检查

本文件只提供容易写错的命令模板和低层检查。执行顺序、参数选择和结果判定以 [SKILL.md](../SKILL.md) 为准；使用前按当前 XiangShan commit 的 Makefile 和 emu `--help` 校正选项。

本技能只生成和运行 Verilator emu。任何情况下不得构建、生成或运行 gsim emu；如果输入归档中已有 gsim，只记录其来源，不将其作为本轮 debug、reproduction 或 after-fix emu。

构建日志可以记录必要的环境键名，但不得原样记录凭据。对 `GITHUB_TOKEN`、`*_API_KEY`、`*_SECRET`、`*_PASSWORD`、webhook、cookie、授权头等值统一写成 `[REDACTED]`；不要直接把 `env` 输出到任务日志。

开始大规模编译前，先从任务 `logs/` 提取原始模拟器实际使用的依赖和配置（例如 `DRAMSIM3 config`、`DRAMSIM3_HOME`、Constantin、ChiselDB）。逐项检查路径、工具和源码接口；缺失时先记录 blocker，不能用未匹配的默认配置做一轮昂贵构建后再补开关。

## 日志初筛

```bash
XIANGSHAN_DEBUG_SKILL_ROOT=/path/to/installed/xiangshan-debug
python3 "$XIANGSHAN_DEBUG_SKILL_ROOT/scripts/triage_logs.py" \
  --format text /path/to/run-or-archive

rg -n -i 'different at pc|mismatch|assert|abort|bad trap|leak|fatal|core .*instrCnt' \
  /path/to/simulator_out.txt /path/to/simulator_err.txt
```

`triage_logs.py` 只提取候选类别、信号、最大 `instrCnt` 和已有退出码，不负责区分不同 assertion message。分类结论必须核对原始日志并按 [failure-taxonomy.md](failure-taxonomy.md) 归一化 assertion message；脚本未识别的首错或无法判断是否应合并的 message 应在任务 `issues.md` 中单独记录。

## Verilator 调试 emu

任务级在当前任务根目录创建 `XiangShan-original/`，检出确认的 commit 后先执行标准 `make init`，核对依赖完整后冻结源码，从该目录只构建一份共享调试 emu；这个失败用例的所有复现候选和最终代表都使用这份 emu。构建日志统一写入任务根目录的 `build-log/`。调试 emu 使用 `build-debug.log`（共享构建日志的现场副本），修复后 emu 使用 `build-fixed.log`；多个配置或 submodule 使用附加 slug 区分，不能把 build log 写在任务根目录之外。

```bash
export NOOP_HOME=/absolute/path/to/task/XiangShan-original
mkdir -p original
make -C "$NOOP_HOME" init >original/source-init.log 2>&1
INIT_STATUS=$?
printf '%s\n' "$INIT_STATUS" >original/source-init.exit-code
test "$INIT_STATUS" -eq 0 || exit "$INIT_STATUS"
: "${BUILD_LOG_DIR:=/path/to/task/build-log}"
: "${BUILD_JOBS:?Set BUILD_JOBS for this host}"
mkdir -p "$BUILD_LOG_DIR"
make -C "$NOOP_HOME" emu EMU_TRACE=1 WITH_CHISELDB=1 -j"$BUILD_JOBS" \
  >"$BUILD_LOG_DIR/build-debug.log" 2>&1
BUILD_STATUS=$?
printf 'debug emu build exit code: %s\n' "$BUILD_STATUS"
test "$BUILD_STATUS" -eq 0

EMU_REAL=$(readlink -f "$NOOP_HOME/build/emu")
test -n "$EMU_REAL" && test -x "$EMU_REAL"
stat "$EMU_REAL"
sha256sum "$EMU_REAL"
"$EMU_REAL" --help
```

修复后构建使用同样的命令和环境，但先将 `NOOP_HOME` 切换为任务根目录的私有 `/path/to/task/XiangShan/`，再将完整 stdout/stderr 写入 `"$BUILD_LOG_DIR/build-fixed.log"`；不要覆盖 `build-debug.log`，也不要修改任务级 `XiangShan-original/`。

按源码实际接口追加 `CONFIG`、`WITH_DRAMSIM3`、线程等参数。若当前版本的 ChiselDB 变量不同，使用源码定义的名称；不要照搬模板中的变量。

编译或链接错误提示生成物、源码或配置不一致时，核对：

1. FIR/RTL 是否由当前源码和配置生成；
2. C++ model 与对象文件是否来自同一配置；
3. 链接期间是否有并行任务重新生成或清理 model；
4. `build/emu` 最终指向 Verilator 后端和文件时间；如果最终产物指向 gsim，立即停止并记录构建配置错误；
5. ChiselDB、DRAMSim3、Constantin 等开关是否在生成和编译阶段一致。

只清理由证据确认失效的生成物。

## checkpoint 运行包装

```sh
#!/bin/sh
set -u
: "${NOOP_HOME:?Set NOOP_HOME to the XiangShan root}"
: "${EMU:?Set EMU to the copied Verilator debug or fixed emu}"
: "${CHECKPOINT:?Set CHECKPOINT to the representative or candidate checkpoint}"
: "${NEMU:?Set NEMU to the matching reference-model shared object}"
: "${RUN_LIMIT:?Set the execution budget independently of unknown failure positions}"
: "${RUN_DIR:?Set RUN_DIR to the run artifact directory}"

RUN_LIMIT_KIND=${RUN_LIMIT_KIND:-instr}
case "$RUN_LIMIT_KIND" in
  instr) set -- -I "$RUN_LIMIT" ;;
  cycle) set -- -C "$RUN_LIMIT" ;;
  *)
    printf 'Invalid RUN_LIMIT_KIND: %s\n' "$RUN_LIMIT_KIND" >&2
    exit 2
    ;;
esac
mkdir -p "$RUN_DIR"
"$EMU" -i "$CHECKPOINT" \
  --diff "$NEMU" \
  --enable-fork "$@" \
  >"$RUN_DIR/simulator_out.txt" \
  2>"$RUN_DIR/simulator_err.txt"
EMU_STATUS=$?
printf 'emu exit code: %s\n' "$EMU_STATUS"
exit "$EMU_STATUS"
```

这一个用例一次只启动一个 emu invocation，并为它设置独立的 `RUN_DIR` 和运行时模型输出目录。参数名称、fork 行为与终止消息以当前 emu `--help` 和参数实现为准；外层 `timeout` 只用于明确标注的 smoke。部分版本在参数解析后会关闭 parent 的常规 waveform，但在失败时由 `fork_child_init()` 唤醒 child、强制开启波形；这种实现仍可使用 `--enable-fork`，前提是实际生成非空波形，并把同一次 invocation 的 parent/child 日志、退出状态和真实波形路径一起固化。若当前版本没有该 child 波形机制，再使用可验证的非 fork 带波形运行。

如果这一个 checkpoint 需要重试，使用 `reproduction/candidates/<attempt-slug>/` 记录每次有明确目的的参数变化；不能把其他 checkpoint 当成替代代表，也不能并发启动多个相同用例来碰运气。每次结束后保留 stdout/stderr 和退出码，只有日志首错匹配且波形已写完，才把该次证据提升到 `reproduction/` 根部。仍不能复现时保留尝试并明确证据缺口，不生成空波形。

仿真输出必须直接流式写入文件；不要在 Python `PIPE` 中积攒数 GB 的 stdout/stderr。父进程退出后，在限定等待窗口内轮询本次 `RUN_DIR` 的 `build`/波形目录，且只选择本次 invocation 新生成的非空 FST/VCD。不要递归扫描整个源码树，也不要使用其他任务的缓存波形。归档前将 `build/emu` 等绝对路径符号链接解析为任务目录内的普通文件，并记录二进制 sha256。

`RUN_LIMIT` 是本次执行的最终上限，`RUN_LIMIT_KIND` 选择指令数（`instr`，默认）或周期数（`cycle`）。已知首错 `instrCnt` 时，可取 `instrCnt + RUN_MARGIN`；只有 cycle 时，可取 `cycle + RUN_MARGIN` 并选择 `cycle`。`RUN_MARGIN` 可默认取 `10000`，按所需观察窗口调整，不是新的错误位置。首错位置未知时，根据用例和可用资源单独选择运行预算。保存实际 `-I/-C`、退出原因和观测到的计数；基线正常达到 limit 且未出现首错只能判为“未重现”。

每次调整上限或其他参数，都应记录所检验的假设、参数差异、预期结果和停止条件。达到既定运行预算或没有新的调查依据时停止，保留全部尝试日志。

原始日志没有出错节点的 `instrCnt` 或 cycle 时，`checkpoints.txt` 对应字段写 `unknown`。选定的 `RUN_LIMIT`、选择依据和实际执行计数记录到 `execution.md`；不能用运行预算代替日志观测到的错误位置。

## patch 检查

```bash
: "${BASE_COMMIT:?Set BASE_COMMIT to the recorded original commit}"
git -C /path/to/case/XiangShan diff --check
git -C /path/to/case/XiangShan diff --binary "$BASE_COMMIT" -- \
  > /path/to/task/patch/patch.diff
```

主仓和 submodule 有改动时分别在各自仓库执行，并在 `message.txt` 记录 patch 应用顺序。
