# XiangShan RTL Simulator Performance Counter Analysis Guide

This guide instructs an agent to analyze XiangShan RTL simulation logs named `simulator_err.txt`. The goal is not to list counters mechanically, but to build an analysis chain based on performance counters: "symptom -> evidence -> judgment -> uncertainty". Use this chain to locate performance changes in the frontend, backend, memory system, and related modules.

## Scope

Use this workflow when the user provides one or more `simulator_err.txt` files, or simulation result directories that contain this file. If the user asks for a base/new comparison or a comparison across multiple experiment directories, output a comparison report by default. The report should include raw values, normalized metrics, and deltas for key counters.

## File And Phase Selection

`simulator_err.txt` is the stderr output collected during XiangShan simulation. It contains runtime logs and performance counters. Performance analysis usually uses only the performance counter sections. Do not treat normal logs, warnings, or assert messages as performance data.

The same performance counter usually appears twice:

| Occurrence | Meaning | Default handling |
| --- | --- | --- |
| First | Warmup phase statistics | Do not use for performance conclusions |
| Second | Actual simulation phase statistics | Use for IPC, MPKI, hit rate, coverage, and other metrics |

Default rules:

1. Unless the user explicitly asks to analyze warmup, use counters from the actual simulation phase.
2. If the same counter appears multiple times, prefer the value near the end of the file, corresponding to the actual simulation phase.
3. Do not add warmup and actual simulation values for the same counter.
4. If the phase cannot be identified, state this uncertainty in the report.

## General Reading Rules

1. When comparing two or more results, first confirm that the benchmark, input, simulation interval, and configuration switches are comparable.
2. For percentages, hit rates, accuracy, and other derived metrics, keep both numerator and denominator.
3. If the denominator is 0, report the metric as `N/A`; do not force it to `0%`.
4. Normalize absolute counts to `cycles` or `committed instructions` whenever possible.
5. Module-level conclusions must check both upstream and downstream evidence to avoid treating a symptom as the root cause.
6. If key counters are missing, provide a limited conclusion based on available evidence, then explicitly list the missing counters and data that should be added.

## Basic Counter Semantics

Counter names may differ across XiangShan versions. Match counters by semantic meaning instead of relying on one fixed name.

| Category | Common counter semantics | Purpose |
| --- | --- | --- |
| Cycles | cycle, clock, perfCnt cycle | Calculate IPC, bandwidth, and ratios |
| Commit | committed instruction, commitInstr, instrCnt | Standard denominator |
| Frontend | fetch, ifu, ftq, ittage, ras, ubtb, btb, tage | Identify fetch and prediction bottlenecks |
| Backend | dispatch, issue, execute, writeback, commit, rob | Identify backend stalls and execution bottlenecks |
| Memory access | load, store, lsq, ldq, stq, sbuffer | Analyze memory instructions, replays, and stalls |
| Cache | l1, l2, l3, miss, hit, mshr, probe, refill | Calculate hit rate, MPKI, and cache pressure |
| TLB | itlb, dtlb, ptw, tlb miss | Analyze address translation overhead |
| Prefetch | prefetchSent, prefetchHit, prefetchLate, prefetchUseless | Evaluate prefetch effectiveness |

## Common Normalized Metrics

Let:

```text
cycles = cycle count in the actual simulation phase
instrs = committed instruction count in the actual simulation phase
counter = value of a counter in the actual simulation phase
```

Common metrics:

| Metric | Formula | Meaning |
| --- | --- | --- |
| IPC | `instrs / cycles` | Main top-level performance metric |
| CPI | `cycles / instrs` | Average cycles per instruction |
| per-cycle | `counter / cycles` | Throughput, occupancy, or event density |
| per-kilo-instr | `counter * 1000 / instrs` | Events per thousand instructions, often used for misses |
| rate | `numerator / denominator` | Hit rate, stall rate, accuracy, and similar ratios |
| delta | `new - base` | Absolute change |
| delta% | `(new - base) / base` | Relative change |

Comparison output should include `base`, `new`, `delta`, and `delta%` by default. If there are multiple experiments, show base in one column and, for each experiment, show the value and the change relative to base.

## Analysis Workflow

### 1. Confirm Result Comparability

Check the following items first:

| Check item | How to judge |
| --- | --- |
| Same benchmark | Log path, command line, workload name |
| Same simulation interval | warmup, simpoint, max instruction, commit count |
| Same configuration | core parameters, cache parameters, prefetcher, branch predictor, switches |
| Complete run | Normal termination, early exit, assert/fatal messages |

If the committed instruction count in the actual simulation phase differs significantly, explain the reason before making a performance comparison. If the reason cannot be explained, lower the confidence of the conclusion in the report.

### 2. Calculate Top-Level Performance

Calculate these first:

```text
IPC = committed instructions / cycles
CPI = cycles / committed instructions
```

If IPC decreases, first look for counters such as `topdown` or `rob*wait*cycle` that can break down waiting cycles. Use them to determine whether the dominant change comes from:

1. Insufficient frontend supply.
2. Backend execution or resource limits.
3. Memory latency or bandwidth pressure.
4. Commit-side stalls or flush loss.

### 3. Analyze The Frontend

Frontend analysis focuses on fetch bandwidth, prediction quality, frontend buffers, and frontend stalls.

Common patterns:

| Symptom | Possible cause |
| --- | --- |
| Lower fetch/commit throughput | Insufficient frontend supply or backend backpressure |
| More branch misses, redirects, or flushes | Lower branch prediction accuracy |
| Abnormal empty/full cycles in FTQ, fetch buffer, or instruction buffer | Frontend/backend coupling issue |
| Higher ITLB miss or I-cache miss MPKI | Instruction-side memory bottleneck |

Recommended metrics:

```text
branch MPKI = branch miss * 1000 / instrs
redirect MPKI = redirect count * 1000 / instrs
frontend stall ratio = frontend stall cycles / cycles
icache miss MPKI = icache miss * 1000 / instrs
```

### 4. Analyze The Backend

Backend analysis focuses on dispatch, issue, execution units, ROB, and commit stalls.

Common patterns:

| Symptom | Possible cause |
| --- | --- |
| More dispatch stalls | Insufficient ROB, IQ, LSQ, physical registers, or rename resources |
| Lower issue throughput | Longer dependency chains, functional unit contention, wakeup/select issues |
| More ROB full cycles | Long-latency operations or memory misses blocking commit |
| Lower commit throughput | Exceptions, flushes, load violations, long-latency instructions |

Recommended metrics:

```text
dispatch utilization = dispatch count / cycles
issue utilization = issue count / cycles
commit utilization = committed instructions / cycles
rob full ratio = rob full cycles / cycles
```

### 5. Analyze The Memory System

Normalize memory-system counters to MPKI, per-instr, or per-cycle first.

Common metrics:

```text
load MPKI = load miss * 1000 / instrs
store MPKI = store miss * 1000 / instrs
l1 miss rate = l1 miss / l1 access
l2 miss rate = l2 miss / l2 access
mshr full ratio = mshr full cycles / cycles
replay MPKI = replay count * 1000 / instrs
```

Suggested diagnosis order:

1. Check whether L1 misses increased.
2. Check whether L2 misses increased.
3. Check whether MSHR full, bank conflict, replay, or nack increased.
4. Check whether load-to-use latency or stall cycles increased.
5. Check whether store buffer or store queue backpressure appeared.

If L1 misses increase but L2 misses do not, possible explanations include locality changes between cache levels, a changed prefetch hit location, or changed access behavior. If L2 misses also increase, continue checking prefetching, replacement, bandwidth, and memory-side pressure.

## Comparison Report Template

Suggested output structure:

```text
Conclusion:
- IPC changed from A to B, a C% change.
- The main change comes from module X: key counter M changed from A to B, and MPKI/rate changed by C.
- Secondary effects include Y and Z.

Top-level metrics:
| Metric | base | new | delta | delta% |

Key modules:
| Counter/metric | base | new | delta | delta% | Explanation |

Root-cause judgment:
1. Direct evidence.
2. Supporting evidence.
3. Counter-evidence or missing counters that still need confirmation.
```

## How To Write Conclusions

Write conclusions as "metric change + performance meaning + evidence chain". Avoid only listing counters.

Example:

```text
The IPC drop is mainly caused by increased L2-side memory pressure. In the actual simulation phase, L2 demand miss MPKI increased, and the MSHR full cycle ratio also increased. This shows that misses did not only increase in count; they also caused stronger blocking on concurrent miss resources.
```

When evidence is insufficient, state it explicitly:

```text
The current counters confirm that L1 miss MPKI increased, but they cannot distinguish whether the cause is the replacement policy, prefetch pollution, or a changed access stream. Additional replacement, prefetch useless, prefetch late, and MSHR occupancy counters are needed.
```

## Common Pitfalls

| Pitfall | Correct handling |
| --- | --- |
| Using warmup counters for conclusions | Use the second occurrence by default, corresponding to actual simulation |
| Looking only at absolute counts | Normalize by cycles or committed instructions |
| Looking only at rate | Check both numerator and denominator |
| Looking only at IPC | Build a frontend/backend/memory evidence chain |
| Reporting 0% when denominator is 0 | Report N/A |
| Directly comparing results with different commit counts | Explain the simulation interval difference first |
| Treating higher prefetch hit rate as necessarily better | Also check demand miss, useless, late, drop, and bandwidth pressure |
| Treating higher miss count as a cache regression | Check access count, instruction count, prefetching, and upstream behavior |

## Minimum Analysis Checklist

For any comparison between two `simulator_err.txt` files, report at least:

1. Whether counters from the actual simulation phase were used.
2. committed instructions, cycles, and IPC.
3. The MPKI or cycle-ratio metric with the largest change.
4. Which category among frontend, backend, and memory is most likely to dominate the change.
5. A key evidence table.
6. Explicit uncertainties and counters that should be added.

<!-- This guide is still coarse. It can be refined module by module in practice, for example with concrete counter names and concrete decision trees. -->
