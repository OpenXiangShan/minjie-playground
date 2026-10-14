# Root-Cause Analysis and Fix Validation

Use this reference to identify the earliest causal failure and validate the smallest fix. Follow the
relevant instruction, request, or state; do not force every failure through the same pipeline.

## 1. Record the first error and relevant state

Preserve evidence from the same run:

- the first-error signature and full text, with observed PC, instruction, count, cycle, expected value,
  and actual value when applicable;
- the dynamic object and state relevant to the failure: commit records for architectural mismatches,
  blocked instructions or resources for stuck/liveness, assertion context for protocol failures, and
  host exception or stack information for fatal errors;
- seed, checkpoint, configuration, reference model, and emu identity.

An `ABORT` or mismatch PC may only identify where the difference was detected. For an architectural
mismatch, trace the wrong register or memory value back to the producer using the relevant log,
waveform, and source. Use commit traces and matching disassembly when they are relevant.

## 2. Follow the relevant lifetime

Select the stages required by the observed causal path. Record time, dynamic identity, valid or enable
state, handshakes, key inputs and outputs, and state transitions. Find the first point at which the
expected invariant or progress condition is lost.

Label conclusions as:

- **Waveform fact**: directly shown by a waveform or log.
- **Source meaning**: the field or signal meaning established from the matching Chisel/RTL source.
- **Candidate cause**: an inference with alternatives still open.
- **Verified cause**: explains the first error and is covered by the fixed-run evidence.

## 3. Exclude alternative explanations

Check the inputs and evidence relevant to this failure:

1. checkpoint, ELF, NEMU, and seed identity;
2. waveform, RTL, source commit, generated artifacts, and configuration;
3. any earlier independent mismatch, assertion, or limit;
4. waveform time origin versus difftest `cycleCnt`, especially after a fork or checkpoint;
5. signal path, width, and valid/ready semantics against source.

If a key check cannot be completed, report “insufficient evidence.” Do not promote a similar PC,
statistical coincidence, or normal fixed exit to a root-cause conclusion.

## 4. Minimal fix and condition coverage

Apply only a fix supported by causal evidence and keep the baseline read-only. Besides running difftest
on the same checkpoint, provide at least one direct observation: a focused waveform, cover point, counter,
assertion, or equivalent. It must show that the original trigger occurs in the fixed run and that the
fixed behavior satisfies the invariant.

When the first-error position is known, the fixed run must go beyond it without the original or a new
functional error. If the run reaches its limit after the trigger is covered and difftest is clean, report
"validated over the executed range," including the limit and termination reason; do not claim coverage of
the full workload. If the trigger is not observed, report "insufficient validation."
