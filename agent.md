# FPGA Usage Lock Guide

This repository uses [`scripts/fpga_usage.sh`](scripts/fpga_usage.sh) to coordinate access to the shared VU19P FPGA.

## Status Files

The script operates on the FPGA host and writes under:

```text
~/.fpga_used/
```

Default files for the VU19P board:

```text
~/.fpga_used/vu19p.status
~/.fpga_used/vu19p.in_use
~/.fpga_used/vu19p.idle
```

## Required Workflow

Before touching the board:

```sh
make fpga_init REMOTE=fpga REMOTE_DIR=/path/to/minjie-playground
make fpga_status REMOTE=fpga REMOTE_DIR=/path/to/minjie-playground
```

Normal top-level FPGA commands already enforce the check automatically:

```sh
make write_bitstream ...
make write_jtag_ddr ...
make reset_cpu ...
make run_host ...
```

If another user has already marked the board busy, these commands fail before programming the FPGA.

## Manual Control

When you need to reserve or release the board explicitly:

```sh
make fpga_claim REMOTE=fpga REMOTE_DIR=/path/to/minjie-playground
make fpga_release REMOTE=fpga REMOTE_DIR=/path/to/minjie-playground
```

`make run_host` releases the board automatically when `fpga-host` exits. If you stop after programming, DDR write, or reset without running `fpga-host`, release the board manually.
