# Debug Flow

This document defines a structured process for multi-step FPGA DiffTest debugging.

For simple issues, start with [troubleshooting.md](./troubleshooting.md).

## When to Use This Flow

Use this flow when:

- The root cause is not obvious from the first error message
- Multiple hypotheses need to be tested in sequence
- The issue spans RTL, DiffTest, NEMU, workload, XDMA, or FPGA runtime
- You need to keep notes across multiple sessions

## Job Directory Structure

Create one directory per investigation under `jobs/`:

```text
jobs/<job-id>/
├── debug-plan.md
├── progress.md
├── commands.sh
├── summary.md
├── problem-analysis.md
└── logs/
```

Use a stable `<job-id>` that makes the investigation easy to identify later.

## Phase 1: Write the Debug Plan

Before running debug steps, create `debug-plan.md` with these sections:

1. **Problem Statement**
   - What is observed
   - What is expected
   - How to reproduce

2. **Hypotheses**
   - Ordered list of possible causes

3. **Debug Steps**
   - Command to run
   - Expected result if the hypothesis is correct
   - Expected result if the hypothesis is wrong
   - Next action after the result

4. **Pass/Fail Criteria**
   - What counts as resolved
   - What counts as escalation

Example outline:

```markdown
# Debug Plan: <job-name>

## Problem Statement
<observed behavior>

## Hypotheses
1. <hypothesis-1>
2. <hypothesis-2>

## Debug Steps
### H1
- Run: `<command>`
- If true: <expected result>
- If false: <expected result>
- Next: <next action>

## Pass/Fail Criteria
- PASS: <success condition>
- FAIL: <escalation condition>
```

## Phase 2: Track Progress

Update `progress.md` immediately after each step.

Recommended structure:

~~~markdown
# Progress: <job-name>

## Environment
- Build host: <BUILD_REMOTE>
- Vivado host: <VIVADO_REMOTE>
- FPGA host: <FPGA_REMOTE>
- Release: <RELEASE_PATH>
- Bitstream: <BIT_PATH>
- Workload: <WORKLOAD_PATH>

## Step Log

### Step 1 — <step title>
Command:
```sh
<command>
```

Result:
<what happened>

Decision:
<what you concluded and what you will do next>
~~~

Rules:

- Record the exact command
- Record the important output or store the full output in `logs/`
- Record the decision after each step
- If the plan changes, update `debug-plan.md`

## Phase 3: Maintain a Summary

Keep `summary.md` updated during the investigation.

Required contents:

1. **Goal / Problem**
2. **Changes Made**
3. **Tests / Runs Performed**
4. **Artifacts and Paths**
5. **Key Conclusions**
6. **Final Result**

Use placeholders such as `<BIT_PATH>`, `<WORKLOAD_PATH>`, `<RELEASE_PATH>`, and `<HOST_PATH>` until the final concrete values are known.

## Phase 4: Write the Final Analysis

When the issue is resolved or explicitly deferred, write `problem-analysis.md`.

Suggested structure:

```markdown
# Problem Analysis: <job-name>

## Root Cause
<root cause>

## Fix Applied
<fix or mitigation>

## Verification
<how the result was verified>

## Follow-up
<remaining risks or next steps>
```

## Debugging Escalation Levels

When troubleshooting DiffTest comparison failures, use this escalation:

| Level | Tool | When to use |
|-------|------|------------|
| 1 | Console output | First pass: identify failing checker, cycle, DUT vs REF state |
| 2 | Query DB | Console output is insufficient for precise state comparison |
| 3 | Waveform | Query DB is still insufficient for signal-level analysis |

For Level 2 and Level 3 details, refer to [`difftest/docs/test.md`](../../difftest/docs/test.md).

## Checklist

Before starting:

- [ ] Create `jobs/<job-id>/`
- [ ] Write `debug-plan.md`
- [ ] Start `progress.md`
- [ ] Create `summary.md`

During the investigation:

- [ ] Update `progress.md` after each step
- [ ] Keep `summary.md` current
- [ ] Save large outputs under `logs/`
- [ ] Revise `debug-plan.md` if the strategy changes

After the investigation:

- [ ] Finalize `summary.md`
- [ ] Write `problem-analysis.md`
- [ ] Record the final result clearly
