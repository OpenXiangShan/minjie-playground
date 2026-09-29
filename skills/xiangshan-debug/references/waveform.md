# Verilator 波形分析 Workflow

本文件只负责分析已经存在的 Verilator 波形，不负责生成波形。波形通常是 VCD，也可能是 FST；默认示例使用 VCD，执行时按实际文件路径设置 `WAVE`。波形、日志和 XiangShan 源码必须来自同一 commit/config；不使用 gsim 生成或运行波形。

波形由复现运行步骤产生，保存位置和初始/修复版本边界以 [SKILL.md](../SKILL.md) 与 [reproduction-delivery.md](reproduction-delivery.md) 为准。本流程直接调用当前 Python 环境中的 `pywellen`，不依赖额外的波形 CLI、缓存层、RTL parser 或 bundled runtime。

## 1. 固化输入与分析目录

查询前确认以下输入来自同一构建：

- 已存在的 `wave.vcd` 或 `wave.fst`；默认按 VCD 处理，FST 仅替换 `WAVE` 路径。
- 失败日志中的 cycle、PC、指令或请求信息。
- 同一 commit/config 的 `XiangShan-original` 或类别私有源码。
- 可选的同一构建 `build/rtl`；没有它时只能做 waveform-only analysis。

建议只把一次性查询结果放在类别目录的 `reproduction/analysis/`，不把缓存或脚本写入生产 skill 目录：

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

确认当前 Python 环境能导入 `pywellen`：

```bash
python3 -c 'import pywellen; print("pywellen: available")'
```

如果导入失败，先在当前 Python 环境安装或启用 `pywellen`，并在分析记录中保存依赖错误；不能猜测波形信号值。

## 2. 打开波形并筛选候选信号

`pywellen.Waveform` 根据扩展名和文件内容读取 VCD/FST。大型 XiangShan 波形可能包含数百万个变量；默认不得把 `wave.all_vars()` 的完整结果写入文件、转成 `list`/`set`，也不得把完整信号表回显到模型上下文。如果提供了香山代码和verilog代码，可以通过阅读相关的代码，理解行为来筛选关键的信号。应在单次迭代中按当前错误的模块、信号名称、字段和后缀过滤，只持久化小型候选集，同时记录扫描总数和是否截断。只有窄过滤无法定位且报告明确说明原因时，才逐步放宽关键词，仍不生成全量清单。

下面的代码只使用 `pywellen` 和 Python 标准库，不需要当前 skill 的辅助脚本。先根据日志和源码把 `TOKENS` 改成当前问题所需的最小集合；`MAX_MATCHES` 是防止候选输出失控的硬上限：

```bash
WAVE=/absolute/path/to/reproduction/wave.vcd
ANALYSIS=/absolute/path/to/reproduction/analysis
mkdir -p "$ANALYSIS"

WAVE="$WAVE" OUT="$ANALYSIS/signal-candidates.txt" python3 - <<'PY'
import os
from pathlib import Path
import pywellen

TOKENS = ("decode", "commit", "illegal", "trapinstinfo")
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

如果实际文件是 FST，只把 `WAVE` 改成 `wave.fst`；其余代码不变。信号的完整路径以筛选后的 `signal-candidates.txt` 和后续精确查询为准，不能凭模块名称猜测路径。若候选达到上限，先收紧模块层级、字段后缀或源码推导出的实例名，不要提高上限来保存全设计信号。

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
wave = pywellen.Waveform(path=os.environ["WAVE"], remove_scopes_with_empty_name=False)
known = {var.full_name for var in wave.all_vars()}
missing = [name for name in signals if name not in known]
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

wave.stream_changes(collect, signals)
Path(os.environ["OUT"]).write_text(
    json.dumps({"start": start, "end": end, "signals": signals, "changes": changes}, indent=2) + "\n",
    encoding="utf-8",
)
print(f"changes: {len(changes)}")
PY
```

`stream_changes` 返回的 `signal_id` 需要结合 `signal-candidates.txt` 中的路径映射解释；不要仅凭 ID 推断信号名称。没有 `build/rtl` 时，查询结果只包含 waveform-only evidence；有 `build/rtl` 时，也必须手工核对 RTL 信号与同一 commit 的 Chisel 源码，不能把未经验证的名称匹配当作精确归属。

## 4. 查看顺序与判定

从错误 cycle 向前查看一个有限窗口，依次检查：

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
- `pywellen` 不可用：在当前 Python 环境安装或启用依赖，记录导入错误，不猜测信号值。
- 信号路径不存在：对 `wave.all_vars()` 做一次流式、关键词受限的候选筛选；逐步调整模块/字段关键词，不生成或保存完整信号清单。
- RTL 与 waveform commit 不一致：停止查询，重新选择同一 commit/config 的 RTL 和波形。
