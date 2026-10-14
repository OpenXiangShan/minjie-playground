# Failure Signatures and Investigation Directions

This table selects an investigation direction. It does not replace the first-error procedure or the
validation criteria in [SKILL.md](../SKILL.md).

| Type | Typical signature | Preserve first | Start with |
| --- | --- | --- | --- |
| `stuck` | No instruction commits for a configured cycle interval | core, interval, last committed PC/instruction, commit trace, blocked state | commit path, head state, redirect/flush, fetch/execute progress, memory or coherence response |
| `liveness` | watchdog, deadlock, livelock, or resource leak | last progress, entry/request identity, timer, backpressure | allocation/free, arbitration, queues, state progress, downstream blocking |
| `mismatch` | register, CSR, memory, control-flow, or commit-order difference | PC/instruction, expected/actual state, commit sequence, address/request data | producer, forwarding, writeback, rename/commit, translation, cache, ordering, redirect |
| `assertion` | assertion or protocol invariant failure | full message, normalized template, RTL hierarchy, time, related state | valid/ready/fire, allocation/free, counters, state machine, response matching |
| `bad_trap` | `HIT BAD TRAP` or `ABORT` | trap code, PC, exit path, earlier errors | workload exit, exception handling, difftest, cascading failures |
| `fatal` | fatal error, segmentation fault, or core dump | host stack, signal, final output, exit code | simulator, dependency, generated-artifact, and design-trigger paths |

The standard no-commit message is `stuck`, even when a later reference-model mismatch or `ABORT` appears.
If an independent error precedes that message, establish the first error from the original log order.
Treat build failures, artifact mismatches, normal limits, host timeouts, missing archives, and seed/backend
differences as evidence or environment problems until the log establishes a functional failure.

For assertion grouping, preserve the complete message and normalize only instance-specific numbers such as
addresses, IDs, counters, and line numbers. Keep module names, conditions, operations, states, and protocol
meaning. Normalization describes the current failure signature; it does not add checkpoints or cases to
the task. If the semantic role of a number is unclear, record the uncertainty in `issues.md`.
