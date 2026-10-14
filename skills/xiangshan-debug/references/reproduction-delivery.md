# Reproduction and Delivery Contract

This reference defines the evidence layout for one failure. The workflow, build options, and verdicts are
controlled by [SKILL.md](../SKILL.md).

## 1. Root files

- `README.md`: a short owner-facing summary with current status, failure, root cause, fix, validation,
  and links to real artifacts.
- `plan.md`: scope, steps, and acceptance criteria.
- `execution.md`: source/configuration identity, commands, selected environment keys, exit codes, limits,
  and progress.
- `issues.md`: actual gaps, blockers, and decisions.
- `bug-analysis.md`: classification, first error, root-cause reasoning, and evidence index.
- `checkpoints.txt`: one tab-separated checkpoint record.
- `report-bug-analysis.md`: first-error and root-cause summary.
- `report-fixed-analysis.md`: patch and validation summary.
- `XiangShan-original/`: frozen baseline source.
- `XiangShan/`: private fix source.

`bug-analysis.md` should identify the workload, checkpoint, report, branch, full source commit, manifest or
supplied artifacts, failure type, first-error signature, observed location fields, and the original and
normalized assertion message when applicable. Include paths and digests for the source and runtime
artifacts, reproduction command and exit code, waveform identity, hypotheses, alternative explanations,
root cause, patch base, and trigger coverage. Keep large logs and query output in their original files or
`execution.md`; mark missing evidence explicitly.

## 2. Checkpoint record

The file is UTF-8 text. Comment lines begin with `#`; data lines use tabs and always have four fields:

```text
# checkpoint_name<TAB>error_instrCnt<TAB>error_cycle<TAB>checkpoint_path
# Use unknown when the log does not provide a location field. Record run budgets in execution.md.
<name>\t<instrCnt-or-unknown>\t<cycle-or-unknown>\t<absolute-checkpoint-path>
```

Do not derive one location field from the other or replace the supplied checkpoint with a similar file.

## 3. Evidence layout

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
    old-emu                  # only when supplied
    analysis/                # only for supplied waveform analysis
      fsdb-export/           # only when FSDB was supplied
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
    candidates/<attempt-slug>/ # only for documented same-case retries
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
    validation/<attempt-slug>/ # only when baseline did not reproduce
      simulator_out.txt
      simulator_err.txt
      exit-code
```

Create conditional directories only when the corresponding evidence exists. Logs, waveforms, and exit
codes must come from the same invocation. Never overwrite supplied logs with reproduction or fixed logs.

## 4. Archive rules

- Freeze `XiangShan-original/` at the verified commit; use it for all baseline runs.
- Use `XiangShan/` only for the patch and fixed emu. Do not modify the frozen tree.
- Keep all build output in `build-log/`, not in source or run directories.
- Store supplied `old-emu` and generated `debug-emu`/`new-emu` as ordinary files; never create gsim to
  fill a missing artifact.
- Record and verify checkpoint paths without copying large checkpoint images into the task.
- Base `patch.diff` on the recorded original commit. Save separate submodule patches when needed.
- Preserve raw stdout/stderr. Put summaries and conclusions in Markdown.
- For FSDB, preserve original identity and conversion records. Check shared access before copying input;
  a large intermediate VCD may stay on the conversion host. Conversion of supplied input is evidence of
  the original failure and cannot be reported as Verilator reproduction. Baseline or fixed exports stay
  in the corresponding run's analysis directory.
- If baseline reproduction fails, retain the attempts and use `after-fix/validation/`; do not call any
  candidate a representative reproduction.
- Fixed validation covers the same checkpoint only. Do not add unrelated workloads or checkpoints.

## 5. Reports

`report-bug-analysis.md`:

```markdown
# Bug Analysis Report

| Item | Result |
| --- | --- |
| Failure type | ... |
| Workload / checkpoint | ... |
| First error | ... |
| Reproduction | ... |
| Root cause | ... |
| Evidence | [`bug-analysis.md`](bug-analysis.md) |
```

`report-fixed-analysis.md`:

```markdown
# Fixed Analysis Report

| Item | Result |
| --- | --- |
| Patch | [`patch/patch.diff`](patch/patch.diff) |
| Fixed emu | [`after-fix/new-emu`](after-fix/new-emu) |
| Representative validation | ... |
| Trigger coverage | ... |
| Remaining risk | ... |
```

Every status must be backed by an actual artifact. Use `insufficient evidence`, `incomplete`, or a named
blocker when validation is missing.
