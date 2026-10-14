---
name: xiangshan-debug
description: >-
  Debug one XiangShan failure: classify it, reproduce it, locate the first violated invariant,
  implement the smallest fix supported by evidence, and validate the same workload and checkpoint.
  Supports VCD/FST analysis and optional FSDB extraction with the available Verdi tools.
  Builds and runs only a Verilator emu with waveform and ChiselDB support; never builds or runs gsim.
---

# XiangShan Debugging

Use this skill for one specified failure and its workload/checkpoint. Complete input validation,
baseline reproduction, waveform analysis, minimal repair, validation of the same case, and delivery.
Keep log facts, hypotheses, and verified conclusions separate.

## Rules

- Treat one task as one failure, workload, and checkpoint. Later cascading errors explain the first error;
  they do not create additional cases.
- Write all task artifacts in the task root. Do not create `cases/` or category directories.
- Build and run only a Verilator emu with waveform and ChiselDB support. Disable PGO. Existing gsim
  artifacts may be recorded as input provenance, but this skill must never build, generate, or run gsim.
- Set `NOOP_HOME` to the XiangShan tree used for each build or run.
- Record only necessary environment keys. Redact tokens, keys, secrets, passwords, cookies, webhooks,
  authorization headers, and similar values as `[REDACTED]`; never archive a raw environment dump.
- Keep `XiangShan-original/` frozen at the verified source commit. Use the separate `XiangShan/` tree
  for the fix.
- Keep baseline evidence under `reproduction/`, fixed evidence under `after-fix/`, and build logs under
  `build-log/`.
- Do not overwrite user changes, supplied logs, or unique waveforms. Do not create empty placeholders.
- Run only one invocation of this case at a time. An emulator fork child is part of that invocation.
  Record compiler parallelism and emulator threading separately.

## Inputs and scope

For an automated task, inspect the root `manifest.json`, `logs/`, and `input/`. For a directly supplied
failure, recover the same metadata from its artifacts and record it in `execution.md`; a manifest is
not required. Confirm the report, workload, official repository URL, branch, full commit, checkpoint,
NEMU, seed, and runtime configuration. Fetch source from the confirmed URL and record the actual commit
and dependency versions.

Use only the supplied workload and its failure log. Missing checkpoints, NEMU, source metadata, or logs
must be recorded in `issues.md` and the reports. Do not substitute files merely because their names look
similar. If the input contains a gsim artifact, record its provenance only.

For a supplied FSDB, record the original path, simulator or FPGA/RTL build, associated log, and
commit/config. Read [fsdb-waveform.md](references/fsdb-waveform.md) when extracting it. Store completed
exports under `original/analysis/fsdb-export/`; they provide evidence of the original failure and do not
replace Verilator reproduction or validation of the fix. If provenance is missing, report waveform facts
without assigning internal signals to unverified source.

Read references only when the current step needs them. Do not echo large logs, full source searches, or
complete waveform signal lists. When writing Markdown or shell containing backticks, `$()`, backslashes,
or variable examples, use a quoted heredoc or equivalent literal method.

Start `plan.md` with the acceptance criteria: baseline first error and waveform, earliest violated
invariant, patch, trigger coverage in the fixed run, and difftest validation of the same case. Keep commands,
handles, exit codes, and results in `execution.md`; keep evidence gaps and decisions in `issues.md`.

## Workflow

### 1. Prepare the baseline

1. Fetch the confirmed official repository into `XiangShan-original/`, check out the full commit, set
   `NOOP_HOME`, and run the commit's standard `make init`; do not substitute a manually selected subset
   of dependencies. Record the real exit code. Verify nested
   submodules, imported build files, and resource links before freezing the tree. Do not use
   `init-force` over user changes. Resolve short commits uniquely; record repository and submodule
   commits and dirty state.
2. Before an expensive build, inspect the original logs for runtime paths, dependencies, and build
   flags (for example DRAMSim3, Constantin, or ChiselDB). Check that required paths and tools exist;
   record blockers before compiling with an unmatched default configuration.
3. Build one debug Verilator emu from the frozen tree with waveform and ChiselDB support, matching the
   recorded configuration. Record the config, core count, compiler jobs, emulator threads, tool versions, and
   relevant runtime settings. Use the current commit's actual option names and disable PGO.
4. Save complete build output in `build-log/build-debug.log`. After a successful exit, confirm the binary
   exists, is executable, and uses Verilator. Record the command, redacted environment, exit code, binary
   digest, and resolved `build/emu` target in `execution.md`.

See [command-reference.md](references/command-reference.md) for templates.

### 2. Classify the failure

1. Triage the logs, then inspect the context around the first error. Use one primary type: `stuck`,
   `liveness`, `mismatch`, `assertion`, `bad_trap`, or `fatal`.
2. The standard message `No instruction of core <id> commits for <cycles> cycles, maybe get stuck`
   is always `stuck`. A later reference-model mismatch, `ABORT`, signal, or assertion is a consequence.
3. Write one checkpoint record to `checkpoints.txt` with the name, observed `error_instrCnt`, observed
   `error_cycle`, and absolute path. Write `unknown` for missing or inapplicable fields; execution
   budgets belong in `execution.md`, separate from observed error positions.
4. In `bug-analysis.md`, record the signature, coarse type, likely subsystem, observed PC/cycle/
   instruction count, expected/actual state, input summary, version, and evidence gaps. Preserve the
   full assertion message. For a mismatch, distinguish the PC that detected it from the producer that
   wrote the wrong state.
5. Update the root `README.md` with the current state, failure, and next step; replace it with the final
   summary at delivery.

See [failure-taxonomy.md](references/failure-taxonomy.md) for signatures and investigation directions.

### 3. Reproduce and inspect waveforms

1. Use the baseline debug emu with the same checkpoint, seed, NEMU, and configuration. Inspect `--help`
   and the parameter implementation first. If a seed is missing, record the chosen substitute and do
   not claim an exact CI replay.
2. Put the first attempt in `reproduction/`. Use `reproduction/candidates/<attempt-slug>/` only for a
   retry of the same checkpoint with a documented hypothesis and parameter change.
3. Logs, exit status, and a non-empty waveform must come from the same invocation. If the current emu
   supports a fork waveform, wait for its child to finish writing before archiving it; otherwise use a
   verifiable non-fork waveform mode. Never select an old or still-growing file.
4. Choose `-I` or `-C` from the observed failure position and required context. Keep the execution limit,
   margin, rationale, and observed counts in `execution.md`. If the position is unknown, choose a
   separate budget instead of inventing an error location.
5. Treat a normal limit without the first error as “not reproduced.” Retry only to test a stated
   hypothesis, and record the changed parameters, expected result, and stopping condition.
6. Read VCD/FST with the current Python environment's `pywellen`. For FSDB, use the conversion reference,
   verify timescale and valid range, calibrate the waveform time to a known signal or commit event, and
   analyze a narrow causal window. Save baseline queries in `reproduction/analysis/` and supplied waveform
   queries in `original/analysis/`.

If bounded retries do not reproduce the failure, retain the attempts and state exactly which inputs or
evidence are still needed. A patch based only on static analysis remains a candidate. A normal fixed-run
exit does not prove the root cause; store this validation in `after-fix/validation/`.

### 4. Isolate the fix and validate it

1. Create `XiangShan/` from the recorded baseline commit. Do not modify `XiangShan-original/`.
2. Follow the relevant instruction, request, or state through its actual lifetime. Locate the first
   invariant violation or loss of progress, recording time, dynamic identity, valid/enable state,
   inputs, outputs, source, and alternative explanations. See [root-cause.md](references/root-cause.md).
3. Implement the smallest fix supported by causal evidence. Run `git diff --check`, build the matching
   fixed emu, and save complete output in `build-log/build-fixed.log`.
4. Write a patch based on the original commit to `patch/patch.diff`, and a proposed commit title/message
   to `patch/message.txt`. Copy the fixed emu as the ordinary file `after-fix/new-emu`.
5. Run the same checkpoint with the original NEMU, seed, and configuration into
   `after-fix/representative/`. When the first-error position is known, run beyond it. Confirm the original
   error and new functional errors are absent, and inspect the full difftest log for architectural
   mismatches. Record the termination reason and actual counts.
6. Use a focused waveform, cover point, counter, assertion, or equivalent observation to show that the
   original trigger occurs in the fixed run and the output satisfies the invariant. Archive any added
   instrumentation patch and binary identity. If the trigger is not observed, report “insufficient
   validation.”
7. Independently check the first error, dynamic object, waveform window, patch base, same-run relationship,
   and fixed result. Update the reports and README; list every remaining blocker.

## Delivery contract

The task root contains the following when the corresponding evidence exists:

```text
<task>/
  README.md                  # owner summary
  plan.md                    # scope and acceptance criteria
  execution.md               # commands, environment, exit codes, progress
  issues.md                  # gaps, blockers, decisions
  bug-analysis.md            # first error, root cause, evidence index
  checkpoints.txt            # one checkpoint record
  report-bug-analysis.md
  report-fixed-analysis.md
  XiangShan-original/         # frozen baseline source
  XiangShan/                 # private fix source
  build-log/build-debug.log
  build-log/build-fixed.log
  original/                  # supplied logs and optional old emu
  reproduction/              # baseline logs, waveform, analysis
  patch/patch.diff
  patch/message.txt
  after-fix/                 # fixed emu and validation
```

Create `reproduction/candidates/`, `original/old-emu`, and `after-fix/validation/` only when real
corresponding evidence exists. Do not fabricate a fixed emu or patch before entering the fix phase.
All links in reports must be relative and point to actual artifacts. See
[reproduction-delivery.md](references/reproduction-delivery.md).

## Boundaries

- Do not run `git commit` by default. Never run `git push` from this debugging workflow.
- Use source metadata verified in the manifest or supplied artifacts, and record the actual source and
  version used.
- Use the current project or user-provided Python environment; do not assume a virtualenv path.
- Before cleanup, confirm that no user change, unique waveform, or original failure artifact will be removed.
- See [github-actions.md](references/github-actions.md) for CI artifacts and [disassembly.md](references/disassembly.md)
  for PC and ELF mapping.
