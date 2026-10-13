# XiangShan 波形分析 Workflow

本文件负责分析已经存在的波形，不负责运行仿真。先按格式选择读取方法：VCD/FST 直接使用 `pywellen`；FSDB 先读取 [fsdb-waveform.md](fsdb-waveform.md)，使用当前环境可用的 Verdi 工具按时间窗口和信号层级导出 VCD/FST，再继续本文件的查询流程。`pywellen` 不直接读取 FSDB。默认示例使用 VCD，执行时按实际文件路径设置 `WAVE`。关联波形、日志和 XiangShan 源码时核对同一 commit/config；不使用 gsim 生成或运行波形。

基线复现波形由复现运行步骤产生，用户提供的 FSDB 及其导出波形属于原始现场证据；保存位置和初始/修复版本边界以 [SKILL.md](../SKILL.md) 与 [reproduction-delivery.md](reproduction-delivery.md) 为准。以下 VCD/FST 查询直接调用当前 Python 环境中的 `pywellen`，不依赖额外的波形 CLI、缓存层、RTL parser 或 bundled runtime。

## 1. 固化输入与分析目录

查询前确认以下输入来自同一构建：

- 已存在的 `wave.vcd` 或 `wave.fst`；FSDB 使用已完成并校验的导出结果，保留原始输入、转换命令、时间窗口及信号选择记录。
- 失败日志中的 cycle、PC、指令或请求信息。
- 同一 commit/config 的 `XiangShan-original` 或任务根目录私有源码。
- 可选的同一构建 `build/rtl`；没有它时只能做 waveform-only analysis。

基线复现的一次性查询结果放在任务根目录的 `reproduction/analysis/`；用户提供现场的转换记录和查询结果放在 `original/analysis/`，修复后的结果放在对应 `after-fix/` 运行目录的 `analysis/`。不把缓存或脚本写入生产 skill 目录。以下以基线复现为例：

```text
reproduction/
  simulator_out.txt
  simulator_err.txt
  exit-code.txt
  wave.vcd or wave.fst
  analysis/
    signal-candidates.txt
    changes-<window>.json
    value-<signal>-<time>.json
```

确认当前 Python 环境能导入 `pywellen`，并记录版本、波形格式和 timescale：

```bash
python3 - <<'PY'
import importlib.metadata
import pywellen

print("pywellen:", importlib.metadata.version("pywellen"))
wave = pywellen.Waveform("/absolute/path/to/reproduction/wave.fst", multi_threaded=True)
print("format:", wave.file_format, "timescale:", wave.timescale)
PY
```

如果导入失败，先在当前 Python 环境安装或启用 `pywellen`，并在分析记录中保存依赖错误；不能猜测波形信号值。

## 2. 打开波形并筛选候选信号

`pywellen.Waveform` 根据扩展名和文件内容读取 VCD/FST。大型 XiangShan 波形可能包含数百万个变量；不要把完整 `wave.all_vars()` 结果另存为列表/集合或回显到上下文。一次遍历只按当前错误的模块、字段和后缀筛选，保存小型候选集、扫描总数和是否截断。没有现成索引不等于波形不可读；只有窄过滤确实无法定位且记录了原因时，才逐步放宽关键词。

下面的代码只使用 `pywellen` 和 Python 标准库，不需要当前 skill 的辅助脚本。先根据日志和源码，将目标模块或字段的关键词以逗号分隔写入 `SIGNAL_TOKENS`；`MAX_MATCHES` 是防止候选输出失控的硬上限：

```bash
WAVE=/absolute/path/to/reproduction/wave.vcd
ANALYSIS=/absolute/path/to/reproduction/analysis
mkdir -p "$ANALYSIS"

: "${SIGNAL_TOKENS:?Set comma-separated keywords for the target module or fields}"
WAVE="$WAVE" SIGNAL_TOKENS="$SIGNAL_TOKENS" OUT="$ANALYSIS/signal-candidates.txt" python3 - <<'PY'
import os
from pathlib import Path
import pywellen

TOKENS = tuple(token.strip().lower() for token in os.environ["SIGNAL_TOKENS"].split(",") if token.strip())
if not TOKENS:
    raise SystemExit("SIGNAL_TOKENS must contain at least one keyword")
MAX_MATCHES = 5000
wave = pywellen.Waveform(
    path=os.environ["WAVE"],
    remove_scopes_with_empty_name=False,
)
scanned = 0
matched = 0
matches = []
for var in wave.all_vars():
    scanned += 1
    name = var.full_name
    lowered = name.lower()
    if any(token in lowered for token in TOKENS):
        matched += 1
        if len(matches) < MAX_MATCHES:
            matches.append(
                f"{name}\twidth={var.bitwidth}\tsignal_id={var.signal_id}"
            )

truncated = matched > len(matches)
header = (
    f"scanned={scanned} matched={matched} matched_saved={len(matches)} "
    f"max_matches={MAX_MATCHES} truncated={str(truncated).lower()} "
    f"tokens={','.join(TOKENS)}"
)
Path(os.environ["OUT"]).write_text(
    header + "\n" + "\n".join(matches) + ("\n" if matches else ""),
    encoding="utf-8",
)
print(header)
PY
```

如果实际文件是 FST，只把 `WAVE` 改成真实 FST 路径；其余代码不变。先用一个已知的 commit/valid 或错误信号确认有效时间范围，再把日志的 `cycleCnt` 与波形时间轴对齐。fork/checkpoint 波形的时间可能从快照开始；FSDB 裁剪导出通常保留绝对时间，但需核对实际工具行为和窗口起始值。两者都不能直接等同于 difftest `cycleCnt`，也不能将窗口起始状态当成真实跳变。

信号的完整路径以筛选后的 `signal-candidates.txt` 和后续精确查询为准，不能凭模块名称猜测路径。若候选达到上限，先收紧模块层级、字段后缀或源码推导出的实例名，不要提高上限来保存全设计信号。

## 3. 直接查询时间点和窗口

查询单个信号在指定时间的最近值：

```bash
WAVE="$WAVE" OUT="$ANALYSIS/value-commit-valid-129500.json" python3 - <<'PY'
import json
import os
from pathlib import Path
import pywellen

signal_path = "TOP.SimTop.cpu.core.rob.commit_valid"
time = 129500
wave = pywellen.Waveform(path=os.environ["WAVE"], remove_scopes_with_empty_name=False)
var = next((item for item in wave.all_vars() if item.full_name == signal_path), None)
if var is None:
    raise SystemExit(f"signal not found: {signal_path}")
result = {
    "signal": signal_path,
    "time": time,
    "value": var.signal.value_at(time),
}
Path(os.environ["OUT"]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(result)
PY
```

查询一个有限时间窗口的变化：

```bash
WAVE="$WAVE" OUT="$ANALYSIS/changes-w125.json" python3 - <<'PY'
import json
import os
from pathlib import Path
import pywellen

signals = [
    "TOP.SimTop.cpu.core.rob.commit_valid",
    "TOP.SimTop.cpu.core.rob.commit_pc",
]
start = 125000
end = 126000
wave = pywellen.Waveform(
    path=os.environ["WAVE"],
    multi_threaded=True,
    remove_scopes_with_empty_name=False,
)
wanted = set(signals)
selected = {}
for var in wave.all_vars():
    if var.full_name in wanted:
        selected[var.full_name] = var
missing = [name for name in signals if name not in selected]
if missing:
    raise SystemExit(f"signals not found: {missing}")
changes = []

def collect(time, signal_id, value):
    if start <= time <= end:
        changes.append({
            "time": time,
            "signal_id": str(signal_id),
            "value": value,
        })

wave.stream_changes(collect, list(selected.values()))
Path(os.environ["OUT"]).write_text(
    json.dumps({"start": start, "end": end, "signals": signals, "changes": changes}, indent=2) + "\n",
    encoding="utf-8",
)
print(f"changes: {len(changes)}")
PY
```

`stream_changes` 的 include 参数使用解析出的 `Var`，回调返回 `(time, signal_id, value)`；用 `str(signal_id)` 映射回 `Var.full_name`，不要仅凭 ID 推断信号名称。没有 `build/rtl` 时，查询结果只包含 waveform-only evidence；有 `build/rtl` 时，也必须手工核对 RTL 信号与同一 commit 的 Chisel 源码，不能把未经验证的名称匹配当作精确归属。

## 4. 查看顺序与判定

从校准后的错误时间向前查看一个有限窗口，依次检查：

1. 模块边界的 `valid`、`ready`、`fire`、backpressure 和 flush；只有 `valid && ready` 才表示 handshake。
2. entry/queue 的 valid、allocate、dequeue、chosen、timer 和状态转移。
3. request ID、地址、opcode、异常/redirect、MSHR 或资源占用。
4. `value_at` 的单点结果和 `stream_changes` 的窗口变化，确认状态是否保持、丢失或错误推进。
5. 将已确认的 RTL signal 回到同一 commit 的 Chisel 源码；粗略映射只能作为辅助，不作为根因证据。

按错误类型选择最小信号集：

- stuck/liveness：commit valid/count、最后提交 PC、ROB head/deq、flush/redirect、阻塞 entry 和资源响应。
- cache/访存：地址、opcode、source/transaction ID、MSHR/queue 状态和每个通道的 handshake。
- assertion：触发 entry 的 valid、分配/释放、arbiter chosen、timer、backpressure 和断言 enable。
- difftest mismatch：commit PC/instruction、写回寄存器/值、异常和 redirect。

结论必须区分 `波形事实`、`源码推断`、`候选根因` 和 `已验证修复`。如果基准 Verilator 没有重演旧错误，只能报告“未重现/证据不足”，不能把修复版正常退出当成根因证明。

## 5. 常见问题

- 波形文件不存在或大小为 `0`：停止查询并记录缺少输入；波形生成属于其他运行步骤，本文件不重新生成波形，也不使用旧日志冒充新波形。
- VCD 和 FST：两者都通过 `WAVE` 传入；默认示例是 VCD，不要把 VCD 的路径或时间单位假定为 FST 的路径或时间单位。
- FSDB：按 [fsdb-waveform.md](fsdb-waveform.md) 先转换；限制时间和信号范围，校验导出边界、所需内部信号及 checksum，再用 `pywellen` 读取 VCD/FST。
- `pywellen` 不可用：在当前 Python 环境安装或启用依赖，记录导入错误，不猜测信号值。
- 信号路径不存在：对 `wave.all_vars()` 做一次流式、关键词受限的候选筛选；逐步调整模块/字段关键词，不生成或保存完整信号清单。
- RTL 与 waveform commit 不一致：停止查询，重新选择同一 commit/config 的 RTL 和波形。
