# Project Layout

## Repository Overview

```text
minjie-playground/
├── Makefile                 # Top-level build orchestrator
├── AGENTS.md                # Agent guidelines (points here)
├── docs/                    # Project documentation
├── difftest/                # DiffTest framework (shared by XS & NutShell)
├── XiangShan/               # XiangShan RTL source
├── NutShell/                # NutShell RTL source
├── NEMU/                    # NEMU reference model
├── workload-builder/        # Workload compilation (Linux & AM)
├── Bin2ddr/                 # Binary-to-DDR-txt converter
├── env-scripts/             # FPGA environment scripts & Vivado projects
│   └── fpga_diff/           # Vivado project, TCL scripts, constraints
├── build/                   # Build outputs (gitignored)
│   ├── build-log/           # Logs for each build stage
│   ├── release/             # Release tarballs and unpacked directories
│   └── run-log/             # fpga-host runtime logs
├── ready-to-run/            # NEMU SO and workload binaries (gitignored)
├── bitstream/               # Bitstream bundles with release (gitignored)
└── jobs/                    # Debug job directories (gitignored)
```

## Component Roles

| Component | Role |
|-----------|------|
| `difftest/` | DiffTest hardware modules + software checkers + FPGA host binary. Linked into both XiangShan and NutShell via `make init`. |
| `XiangShan/` | XiangShan (KunMinghu) RTL. Generates Verilog for FPGA synthesis. |
| `NutShell/` | NutShell RTL. Generates Verilog for FPGA synthesis. |
| `NEMU/` | RISC-V emulator used as the DiffTest reference model. Compiled into a `.so` shared library. |
| `workload-builder/` | Builds Linux and AM (bare-metal) workloads with device trees, OpenSBI, and rootfs. |
| `Bin2ddr/` | Converts a binary image into a `.txt` file for JTAG DDR initialization. |
| `env-scripts/fpga_diff/` | Vivado project files, TCL scripts for synthesis/bitstream, and FPGA operation tools (write bitstream, write DDR, reset CPU). |

## Output Directories

| Path | Contents |
|------|----------|
| `build/release/` | Release tarballs, unpacked releases, `latest-<design>.path` and `latest-<design>.name` |
| `build/build-log/` | Per-stage logs: `verilog-*`, `release-*`, `host-*`, `bit-*`, `nemu-*`, `workload-*` |
| `build/run-log/` | `run_host` runtime logs with timestamps |
| `ready-to-run/<nemu-config>/` | NEMU reference SO (`riscv64-nemu-interpreter-so`) |
| `ready-to-run/<design>-<target>/` | Workload `.bin` and Bin2ddr `.txt` |
| `bitstream/<design>-<time>/` | Bitstream bundle: `.bit`, `.ltx`, and the release directory used for synthesis |
| `jobs/<job-id>/` | Debug job artifacts: plan, progress, commands, logs (see [debug-flow.md](./debug-flow.md)) |

## Key Files

| File | Purpose |
|------|---------|
| `Makefile` | Top-level build targets (`init`, `verilog`, `release`, `host`, `bit`, `nemu`, `workload`, `write_bitstream`, `write_jtag_ddr`, `reset_cpu`, `run_host`) |
| `scripts/fpga_usage.sh` | Shared FPGA occupancy helper for `~/.fpga_used/` on the FPGA host |
| `build/release/latest-<design>.path` | Absolute path to the most recent release (for local use) |
| `build/release/latest-<design>.name` | Release directory name only (for constructing remote paths) |
| `env-scripts/fpga_diff/Makefile` | Vivado build and FPGA operation targets |
| `workload-builder/dts/*.dts.in` | Device tree templates for each platform |
| `difftest/docs/` | DiffTest internal documentation (hardware pipeline, software checkers, config letters) |
