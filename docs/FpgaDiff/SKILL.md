# FPGA DiffTest Documentation Skill

Use this guide when working under `docs/FpgaDiff` or when deciding which FPGA
DiffTest document should be consulted for a task.

## Choose the Document by Scenario

- Use [README.md](./README.md) for the top-level document index and flow
  overview.
- Use [layout.md](./layout.md) when the task is about repository directories,
  generated artifacts, release bundles, bitstream bundles, logs, or
  `ready-to-run` layout.
- Use [workflow.md](./workflow.md) when the task is about the end-to-end build,
  release, bitstream, board programming, reset, or `run_host` flow.
- Use [workload.md](./workload.md) when the task is about AM/Linux workload
  generation, H2C workload images, random memory initialization, or DDR text
  generation.
- Use [host-setup.md](./host-setup.md) when the task is about FPGA host CPU
  performance mode, `perf` hotspot sampling readiness, or run-to-run
  performance comparability.
- Use [xdma.md](./xdma.md) when the task is about XDMA driver build/install,
  `/dev/xdma0_*` nodes, driver loading, PCIe enumeration, or H2C/C2H device
  access.
- Use [troubleshooting.md](./troubleshooting.md) when the task starts from a
  failure symptom, such as PCIe/XDMA issues, host hangs, packet errors, or
  DiffTest mismatches.
- Use [debug-flow.md](./debug-flow.md) when the task is a multi-step
  investigation that needs structured logs, hypotheses, and next actions.

## Editing Guidance

- Keep operational commands tied to the document that owns the scenario.
- Prefer exact paths, artifact names, and log fields over broad descriptions.
- Update [README.md](./README.md) when adding or removing a user-facing
  document.
