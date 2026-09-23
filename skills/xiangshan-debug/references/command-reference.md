# 命令模板与生成物检查

本文件只提供容易写错的命令模板和低层检查。执行顺序、参数选择和结果判定以 [SKILL.md](../SKILL.md) 为准；使用前按当前 XiangShan commit 的 Makefile 和 emu `--help` 校正选项。

本技能只生成和运行 Verilator emu。任何情况下不得构建、生成或运行 gsim emu；如果输入归档中已有 gsim，只记录其来源，不将其作为本轮 debug、reproduction 或 after-fix emu。

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

任务级先创建与 `cases/` 同级的 `XiangShan-original/`，从该目录只构建一份共享调试 emu；所有类别的复现候选和最终代表都使用这份 emu。每个类别现场仍创建 `build-log/`，所有构建命令的 stdout/stderr 都写入该目录。调试 emu 使用 `build-debug.log`（共享构建日志的现场副本），修复后 emu 使用 `build-fixed.log`；多个配置或 submodule 使用附加 slug 区分，不能把 build log 写在类别目录根部。

```bash
export NOOP_HOME=/absolute/path/to/task/XiangShan-original
: "${BUILD_LOG_DIR:=/path/to/case/build-log}"
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

修复后构建使用同样的命令和环境，但先将 `NOOP_HOME` 切换为对应类别的私有 `/path/to/case/XiangShan/`，再将完整 stdout/stderr 写入 `"$BUILD_LOG_DIR/build-fixed.log"`；不要覆盖 `build-debug.log`，也不要修改任务级 `XiangShan-original/`。

按源码实际接口追加 `CONFIG`、`WITH_DRAMSIM3`、线程等参数。若当前版本的 ChiselDB 变量不同，使用源码定义的名称；不要照搬模板中的变量。

出现 helper 未定义、重复 `SSimTop` 或源码中不存在的 C++ 符号时，依次核对：

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
: "${FAILURE_INSTR:?Set FAILURE_INSTR to the original failure instrCnt; use 40000000 for assertion logs without instrCnt}"
: "${RUN_DIR:?Set RUN_DIR to this run's artifact directory}"

RUN_LIMIT=$((FAILURE_INSTR + 10000))
mkdir -p "$RUN_DIR"
"$EMU" -i "$CHECKPOINT" \
  --diff "$NEMU" \
  --enable-fork -I "$RUN_LIMIT" \
  >"$RUN_DIR/simulator_out.txt" \
  2>"$RUN_DIR/simulator_err.txt"
EMU_STATUS=$?
printf 'emu exit code: %s\n' "$EMU_STATUS"
exit "$EMU_STATUS"
```

每个并发运行使用不同的 `RUN_DIR` 和运行时模型输出目录。参数名称与终止消息以当前 emu `--help` 为准；外层 `timeout` 只用于明确标注的 smoke。

初始版本复现时，先把 `RUN_DIR` 设为 `reproduction/candidates/<checkpoint-slug>/` 运行预选 checkpoint；只有该候选稳定复现首错，才将其日志和波形固化到 `reproduction/` 根部。候选不能复现时按记录顺序继续运行同类失败 checkpoint，包含首个候选最多 5 个；全部失败时保留候选日志，不生成代表波形，并在修复后使用 `after-fix/validation/<checkpoint-slug>/` 保存基于日志和源码的回归验证。

主错误类型为 `assertion` 且原始日志没有出错节点的 `instrCnt` 时，调用包装脚本前设置 `FAILURE_INSTR=40000000`；对应 `checkpoints.txt` 的 `error_instrCnt` 写入 `40000000`。如果 cycle 也缺失，`error_cycle` 写入 `unknown`；并在 `bug-analysis.md`、`execution.md` 中说明该指令数是默认回退值，不是日志观测值。

## patch 检查

```bash
: "${BASE_COMMIT:?Set BASE_COMMIT to the recorded original commit}"
git -C /path/to/case/XiangShan diff --check
git -C /path/to/case/XiangShan diff --binary "$BASE_COMMIT" -- \
  > /path/to/case/patch/patch.diff
```

主仓和 submodule 有改动时分别在各自仓库执行，并在 `message.txt` 记录 patch 应用顺序。
