# FPGA DiffTest Documentation

This directory contains the FPGA DiffTest workflow and guides for `minjie-playground`.

## Flow Overview

```text
XiangShan / NutShell Verilog
  -> top-level difftest generates release / fpga-host
  -> env-scripts/fpga_diff generates Vivado bitstream
  -> NEMU generates reference SO
  -> workload-builder compiles workloads
  -> Bin2ddr generates DDR txt for the JTAG fallback/debug path
  -> external-LLC flows write the boot image after every bitstream download
  -> FPGA: write bitstream, restore XDMA, write boot flash when required
  -> fpga-host loads the workload through XDMA H2C by default, then starts DiffTest
```

For UVHS, the runtime host owns download/reset/flash/ILA and the FPGA host owns
the Linux XDMA endpoint and `fpga-host`. The top-level download flow removes and
rescans XDMA around every runtime download. See [workflow.md](./workflow.md) for
the two-host command sequence and UART bridge.

## Common Artifacts

| Path | Contents |
|------|----------|
| `build/release/` | Release tarballs, unpacked releases, `latest-<design>.path`, `latest-<design>.name` |
| `build/build-log/` | Per-stage logs for `verilog`, `release`, `host`, `bit`, `nemu`, `workload` |
| `build/run-log/` | `run_host` runtime logs |
| `ready-to-run/<nemu-config>/` | NEMU reference SO |
| `ready-to-run/<design>-<target>/` | Workload `.bin` for H2C loading, plus Bin2ddr `.txt` for JTAG DDR loading |
| `bitstream/<design>-<time>/` | Bitstream bundle with `.bit`, `.ltx`, and release directory |
| `jobs/<job-id>/` | Debug notes, logs, and summaries for multi-step investigations |

## Document Index

| Document | Contents |
|----------|----------|
| [workflow.md](./workflow.md) | End-to-end flow with optional parameters and per-step examples |
| [layout.md](./layout.md) | Project directory structure, component roles, output directories |
| [workload.md](./workload.md) | Workload compilation for AM and Linux |
| [troubleshooting.md](./troubleshooting.md) | Common issues and debugging approaches: XDMA/PCIe, host hangs, packet errors, DiffTest mismatches |
| [xdma.md](./xdma.md) | XDMA driver build, install, load script, systemd service, troubleshooting |
| [debug-flow.md](./debug-flow.md) | Structured debug flow for multi-step FPGA DiffTest investigations |

## Suggested Reading

1. [layout.md](./layout.md) — Understand the repository structure
2. [workflow.md](./workflow.md) — Follow the end-to-end build and run flow
3. [workload.md](./workload.md) — Customize workload generation
4. [troubleshooting.md](./troubleshooting.md) — Diagnose common failures
5. [debug-flow.md](./debug-flow.md) — Organize longer debugging sessions

For DiffTest internals (hardware pipeline, software checkers, config letters), see [`difftest/docs/`](../../difftest/docs/README.md).
