# Inputs and Archive Layouts

This reference describes common layouts only. Use paths supplied by the task or environment; never infer
an archive root from an unrelated machine.

## SPEC checkpoints

```text
CHECKPOINT_ROOT/
  <checkpoint-version>/checkpoint/<workload>/<instance>/<instance>_<weight>_memory_.zstd
```

Files may end in `.zstd` or `.gz`. Workload names can include compiler, input, and rate fields; match the
actual workload, checkpoint ID, and file rather than parsing a fixed underscore pattern. A checkpoint list
may contain entries such as:

```text
zeusmp_44100 zeusmp/44100 0 0 20 20
```

A typical output directory contains `simulator_out.txt`, `simulator_err.txt`, and optionally `exit-code`.
The same checkpoint can appear under several XiangShan versions, so use the checkpoint list and verified
commit/config to avoid mixing runs.

## ELF and kernel files

A checkpoint root often contains:

```text
CPT_PATH/
  checkpoint/
  elf/
  kernel/
```

Names and directories vary. Confirm the benchmark, input, build, compiler, and digest before using an ELF
or kernel image. See [disassembly.md](disassembly.md) for address mapping.

## Performance and PR archives

Common performance archives look like:

```text
PERF_REPORT_ROOT/cr<date>-<short-sha>-<config>/
  riscv64-nemu-interpreter-so
  <flattened-checkpoint-name>/simulator_out.txt
  <flattened-checkpoint-name>/simulator_err.txt
  <flattened-checkpoint-name>/exit-code
```

PR emu and waveform artifacts may be split across roots by run number and may contain `tar.gz`, `tar.zst`,
`stdout.log`, `stderr.log`, VCD, FST, or FSDB. The archive root must come from the task, CI configuration,
or mount information.

Log names may also use `simulation_out.txt`/`simulation_err.txt`. An empty archive means evidence is
missing; it does not establish whether the run passed. See [github-actions.md](github-actions.md) to
associate archives with their remote runs.

`build/emu` is often a mutable symlink. Resolve it before archiving and verify the backend, source commit,
configuration, modification time, and digest. A path containing `gsim` may be recorded as input provenance,
but must not be used as this skill's emu.
