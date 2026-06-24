# IPC Comparison Performance Analysis Workflow

This workflow instructs an agent to analyze multiple XiangShan performance counter result directories. The user usually provides arguments such as `base=<dir0> exp1=<dir1> exp2=<dir2>`. Each directory records SPEC CPU2006 checkpoint performance results before and after a change.

Example result directory: `/nfs/home/cirunner/perf-report-custom/cr260519-064f8462a-CHIConfig`, where `064f8462a` is usually the commit corresponding to that directory. If the commit cannot be parsed from the directory name, confirm it from the user-provided context or repository state. If it cannot be confirmed, state that in the report.

## 1. Generate The IPC Ranking Table

Run the following command in the minjie-playground repository:

```bash
ANAL_DIR=<your-minjie-playground-path>
python3 $ANAL_DIR/env-scripts/perf/ipc_diff_pro.py \
  /nfs/home/share/checkpoints_profiles/spec06_gcc15_rv64gcb_base_260122/checkpoint-0-0-0/cluster-0-0.json \
  base=<dir0> exp1=<dir1> exp2=<dir2> \
  -o ipc-compare.csv -j8
```

Requirements:

1. Use the absolute path of the current repository for `<your-minjie-playground-path>`.
2. Preserve the user-provided names such as `base=<dir0>` and `exp1=<dir1>`.
3. If the command fails, record the error first, then check paths, permissions, and input directory structure.

`ipc-compare.csv` lists checkpoint information sorted by absolute IPC change from largest to smallest. Common column meanings:

| Column | Meaning |
| --- | --- |
| Checkpoint name column | For example, `gcc_expr2_5858_0.0323863`. The text before the first `_` is usually the benchmark name, and the value after the last `_` is usually the weight |
| Experiment IPC columns | IPC values for each experiment, for example `1.3677760562035624` |
| IPC change columns | IPC change relative to base, for example `0.4789296695484957`; sorting is usually by absolute value |

## 2. Select Key Analysis Targets

Select key checkpoints from `ipc-compare.csv`:

1. Prefer checkpoints with weight greater than `0.1`.
2. Prefer the three distinct benchmarks with the largest IPC decrease.
3. If fewer than three benchmarks qualify, state the filtering result and analyze the available qualified targets.
4. If the user explicitly asks to focus on IPC increases or specific benchmarks, follow the user's request.

The log path for each checkpoint is `<dir>/<checkpoint-name>/simulator_err.txt`, for example:

```text
/nfs/home/cirunner/perf-report-custom/cr260515-d097c4ede-CHIConfig/gcc_expr2_5858_0.0323863/simulator_err.txt
```

## 3. Analyze simulator_err.txt

For each selected checkpoint, follow this process:

1. Refer to `skills/perf-analysis/general-report-rtl-sim-en.md` for general RTL simulation performance analysis.
2. If prefetchers are involved, refer to `skills/perf-analysis/general-report-prefetch-en.md` for additional prefetch-specific analysis.
3. Compare key counters horizontally across experiment directories for the same benchmark.
4. Compare the same metrics vertically across different benchmarks to see whether they show a consistent trend.
5. Every possible cause must be supported by counter values from `simulator_err.txt`.

Do not only write "this may be caused by some module". Provide supporting evidence, such as base/new differences in IPC, MPKI, cycle ratio, accuracy, coverage, drop, stall cycles, and related metrics.

## 4. Combine With Commit Diff

Use the git diff for the commits corresponding to each experiment directory to identify changed functionality or performance logic, then make targeted analysis:

1. Extract the base and experiment commits.
2. Inspect the relevant diff and identify changed modules.
3. In the performance counters, focus on the changed modules and their upstream/downstream modules.
4. The report must explain how counter changes in the modified or related modules affect IPC.

If the corresponding repository or diff cannot be accessed, state clearly in the report that code changes cannot be confirmed and that the conclusion is based only on counters.

## 5. Report Output

Generate a Markdown analysis report at:

```text
<prj_path>/yymmdd-xxx-rpt.md
```

Naming requirements:

1. `yymmdd` uses the current date. For example, June 17, 2026 is `260617`.
2. `xxx` is a short task name that expresses the topic.
3. `rpt` means report.

The report must include at least:

1. Input directories, corresponding commits, and analysis date.
2. IPC ranking summary and the reason for selecting key checkpoints.
3. Top-level IPC/cycles/instructions comparison for each key benchmark.
4. Key module counter comparison tables.
5. Root-cause analysis combined with the diff.
6. Common trends and differences across benchmarks.
7. Final conclusion, evidence strength, and information that still needs to be added.
