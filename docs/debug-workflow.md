# Debug Workflow

This document defines the structured workflow for tackling complex FPGA DiffTest issues that require multiple steps, iterative debugging, or collaboration with sub-agents.

For simple issues (e.g., a single config mistake), refer to [troubleshooting.md](./troubleshooting.md) instead.

## When to Use This Workflow

Use this workflow when:

- The root cause is not immediately obvious from logs or error messages
- Multiple hypotheses need to be tested in sequence
- The fix may span multiple components (RTL, DiffTest, NEMU, workload, XDMA)
- You need to coordinate actions across machines (build server, Vivado server, FPGA host)
- The investigation will span multiple sessions or conversations

## Job Directory Structure

Create a new job directory under `jobs/` for each investigation:

```text
jobs/<YYYYmmdd>-<keyword>/
├── debug-plan.md          # Initial plan with hypotheses and steps
├── progress.md            # Chronological execution log
├── commands.sh            # Reusable commands and helper functions
├── problem-analysis.md    # Root cause analysis (written at conclusion)
└── logs/                  # Collected log files and outputs
```

The `jobs/` directory is gitignored. The naming convention is `<date>-<short-keyword>`, e.g., `20260408-xdma-runhost-flap`.

## Phase 1: Create the Debug Plan

Write `debug-plan.md` before executing any debug steps. The plan must include:

### REQUIRED SECTIONS

1. **Problem Statement**: What is observed, what is expected, and how to reproduce.

2. **Hypotheses**: Numbered list of potential causes, ordered by likelihood.

3. **Debug Steps**: For each hypothesis, specify:
    - The exact command to run
    - The expected output if the hypothesis is correct
    - The expected output if the hypothesis is wrong
    - The next action based on the result

4. **Pass/Fail Criteria**: What constitutes "resolved" vs "needs escalation".

Example structure:

```markdown
# Debug Plan: XDMA Host Flapping

## Problem Statement
fpga-host exits after ~10 seconds with "DMA read timeout" on node fpga.

## Hypotheses
1. XDMA driver version mismatch after kernel update
2. PCIe link instability (signal integrity)
3. DiffTest packet framing error in new release

## Debug Steps

### H1: XDMA driver version
- Run: `modinfo xdma | grep version`
- Expected (if cause): version differs from known-good
- Expected (if not cause): version matches
- Next: if mismatch, rebuild driver; if match, proceed to H2

### H2: PCIe link stability
...

## Pass/Fail Criteria
- PASS: fpga-host runs linux/hello to completion without timeout
- FAIL: timeout persists after all hypotheses tested → escalate to ILA
```

## Phase 2: Execute and Track Progress

Write `progress.md` as you go. **Update it immediately after each step, not at the end.**

### REQUIRED FORMAT

```markdown
# Progress: XDMA Host Flapping

## Environment
- Build host: node004
- FPGA host: fpga
- Release: 20260408_XSTop_..._ESBIFDU_143022
- Bitstream: xiangshan-20260408-143500

## Step Log

### 2026-04-08 14:40 — Check XDMA driver version
```
$ modinfo xdma | grep version
version: 4.6.0
```
Result: matches known-good. H1 ruled out.

### 2026-04-08 14:45 — Check PCIe link status
```
$ sudo lspci -vvv -s 01:00.0 | grep -i "lnk"
LnkSta: Speed 8GT/s, Width x1
```
Result: width is x1, expected x4. Possible signal issue. Investigating.
```

### Key Rules

- Record the **exact command** executed and its **full output** (or put large outputs in `logs/`).
- Record the **decision** made after each step.
- If a step invalidates the plan, note it and update the plan or create a revised version.

## Phase 3: Sub-Agent Delegation

For tasks that require analyzing large log files, inspecting query databases, or searching across many files, delegate to a sub-agent:

| Task | Delegation approach |
|------|-------------------|
| Large log file analysis | Delegate to Explore agent with specific patterns to look for |
| Query DB comparison | Delegate to Explore agent to find the first divergent step |
| Waveform hypothesis | Delegate to Explore agent to check signal values at specific cycles |
| Code search across repos | Delegate to Explore agent for cross-component searches |

When delegating:

1. Provide the sub-agent with **specific questions** and **file paths**.
2. Specify the **thoroughness level** (quick, medium, thorough).
3. Record the sub-agent's findings in `progress.md`.

## Phase 4: Interactive Confirmation

Use `askQuestions` to confirm decisions at critical points:

- Before applying a fix that changes RTL or DiffTest source
- Before rebuilding a bitstream (expensive operation)
- When choosing between multiple viable hypotheses
- At the end of a session, to agree on next steps

## Phase 5: Conclusion

When the issue is resolved (or explicitly deferred), write `problem-analysis.md`:

```markdown
# Problem Analysis: XDMA Host Flapping

## Root Cause
PCIe link negotiating at x1 instead of x4 due to loose cable on lane 2-3.

## Fix Applied
Reseated the PCIe cable. Link now stable at x4.

## Verification
fpga-host ran linux/hello for 5 minutes without timeout.

## Lessons Learned
- Always check PCIe link width before software debugging.
- Add link width check to the pre-run validation script.
```

## Debugging Escalation Levels

When troubleshooting DiffTest comparison failures, follow this escalation:

| Level | Tool | When to use |
|-------|------|------------|
| 1 | Console output | First pass: identify failing checker, cycle, DUT vs REF state |
| 2 | Query DB | Console insufficient: compare DUT and REF state step-by-step |
| 3 | Waveform (FST) | Query DB insufficient: dump and inspect signal-level behavior |

For Level 2 and Level 3 details, refer to [`difftest/docs/test.md`](../difftest/docs/test.md).

## Checklist

Before starting a debug session:

- [ ] Create `jobs/<date>-<keyword>/`
- [ ] Write `debug-plan.md` with hypotheses and steps
- [ ] Start `progress.md` with environment info

During the session:

- [ ] Update `progress.md` after each step
- [ ] Use `askQuestions` for critical decisions
- [ ] Delegate log analysis to sub-agents when appropriate

After resolution:

- [ ] Write `problem-analysis.md`
- [ ] Verify the fix
- [ ] Note any recurring patterns for future reference
