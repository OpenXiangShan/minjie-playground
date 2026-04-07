# FpgaDiff Playground Documentation

## Document Index

| Document | Contents |
|----------|----------|
| [layout.md](./layout.md) | Project directory structure, component roles, output directories |
| [testing-flow.md](./testing-flow.md) | End-to-end testing flow: Verilog → release → host → bitstream → NEMU → workload → FPGA execution |
| [example.md](./example.md) | Complete walkthrough with concrete commands for XiangShan and NutShell |
| [workload.md](./workload.md) | Workload compilation: UART selection (ns16550a vs UARTLite), reg-shift, interrupt routing, NEMU config |
| [troubleshooting.md](./troubleshooting.md) | Common issues and debugging approaches: XDMA/PCIe, host hangs, packet errors, DiffTest mismatches |
| [debug-workflow.md](./debug-workflow.md) | Structured debugging workflow for complex issues: job directories, plan/progress tracking, sub-agent delegation |

## Recommended Reading Order

1. [layout.md](./layout.md) — Understand the repository structure
2. [testing-flow.md](./testing-flow.md) — Understand each build and execution stage
3. [example.md](./example.md) — Walk through a concrete end-to-end run
4. [workload.md](./workload.md) — Reference when building or customizing workloads
5. [troubleshooting.md](./troubleshooting.md) — Reference when diagnosing failures
6. [debug-workflow.md](./debug-workflow.md) — Follow when tackling complex, multi-step debug tasks

For DiffTest internals (hardware pipeline, software checkers, config letters), see [`difftest/docs/`](../difftest/docs/README.md).
