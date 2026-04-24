# Workload Compilation

This document covers workload build options, current XiangShan FPGA DTS usage, UART16550-related settings, and post-build NEMU verification.

## Build Command

```sh
make workload <design> TARGET=<target>
```

The generated workload output directory is:

```text
ready-to-run/<design>-<target>/
```

where `<target>` is `$(subst /,-,$(TARGET))`.

For example:

```sh
make workload xiangshan TARGET=linux/hello
```

produces:

```text
ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.bin
ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.txt
```

## AM Workloads

AM targets are bare-metal workloads such as `am/hello`, `am/coremark`, and `am/riscv-tests`.

For AM targets, the top-level Makefile automatically derives:

| Design | `AM_ARCH` | Extra CPP flags |
|--------|-----------|-----------------|
| `xiangshan` | `riscv64-xs` | `-DUART16550=1` |
| `nutshell` | `riscv64-nutshell` | `-DUART16550=1` |

`-DUART16550=1` selects the UART16550 runtime path in AM.

Example:

```sh
make workload xiangshan TARGET=am/hello
```

Output:

```text
ready-to-run/xiangshan-am-hello/xiangshan-am-hello.bin
ready-to-run/xiangshan-am-hello/xiangshan-am-hello.txt
```

## Linux Workloads

Linux targets are full-system images such as `linux/hello`, `linux/coremark`, and `linux/rvv-bench`.

The assembled firmware image contains:

```text
Offset        Component
──────────    ─────────────────
0x0           GCPT bootloader
+1536 KB      Device tree blob (.dtb)
+1024 KB      OpenSBI (fw_jump)
+2 MB         Linux kernel + initramfs
```

The assembly is performed by `workload-builder/scripts/build-firmware-linux.sh`.

Example:

```sh
make workload xiangshan TARGET=linux/hello
```

Output:

```text
ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.bin
ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.txt
```

## DTS Template: `xiangshan-fpga-noAIA.dts.in`

For the current XiangShan FPGA flow, Linux workloads are built around `workload-builder/dts/xiangshan-fpga-noAIA.dts.in`.

The top-level flow uses `xiangshan-fpga-noAIA.dtb` by default:

```sh
make workload xiangshan TARGET=linux/hello
```

Internally, the flow:

1. Builds the Linux workload image and generated DTBs
2. Picks `workload-builder/build/linux-workloads/<workload>/dt/xiangshan-fpga-noAIA.dtb`
3. Splices that DTB into the firmware image before running Bin2ddr

The template is intentionally FPGA-specific:

- AIA is disabled
- Linux uses the legacy CLINT + PLIC path
- UART16550 is used as the Linux console

Relevant UART16550 section from the current template:

```dts
uart0: serial@310b0000 {
    compatible = "ns16550a";
    reg = <0x0 0x310b0000 0x0 0x10000>;
    reg-shift = <0x2>;
    reg-io-width = <0x4>;
    clock-frequency = <50000000>;
    current-speed = <115200>;
    status = "okay";
};
```

And the console selection in `chosen`:

```dts
chosen {
    bootargs = "console=ttyS0,115200 earlycon loglevel=8";
    stdout-path = "serial0:115200n8";
};
```

### What to Check in This Template

- `reg-shift = <0x2>` means UART registers are spaced at 4-byte intervals
- `reg-io-width = <0x4>` means Linux accesses the UART with 32-bit MMIO
- `clock-frequency = <50000000>` must match the FPGA wrapper
- `stdout-path` and `bootargs` route the Linux console to UART16550

If the hardware wrapper changes, update the DTS template first, then rebuild the workload.

If needed, you can still override the default DTB filename:

```sh
make workload xiangshan TARGET=linux/hello WORKLOAD_DTB=xiangshan-fpga-noAIA.dtb
```

## NEMU and UART16550

For XiangShan-related NEMU configurations, the relevant UART model is `UART16550`.

The current NEMU side uses options such as:

```text
CONFIG_HAS_UART16550=y
CONFIG_UART16550_MMIO=0x310b0000
```

Build the reference SO with:

```sh
make nemu NEMU_CONFIG=<NEMU_CONFIG>
```

Output:

```text
ready-to-run/<NEMU_CONFIG>/riscv64-nemu-interpreter-so
```

If the DTS UART address, width, or console routing diverges from the NEMU UART16550 model, Linux boot and DiffTest UART accesses can fail or mismatch.

## Verify the Built Workload with NEMU

After building the workload, you can do a quick standalone check with NEMU before going to FPGA.

1. Build the workload:

   ```sh
   make workload <design> TARGET=<target>
   ```

2. If needed, build the corresponding NEMU binary/config first:

   ```sh
   cd NEMU
   make <NEMU_CONFIG>
   make -j
   ```

3. Run the generated image with NEMU in batch mode:

   ```sh
   ./build/riscv64-nemu-interpreter /path/to/minjie-playground/ready-to-run/<design>-<target>/<design>-<target>.bin
   ```


For AM workloads, this is a quick sanity check for boot and trap behavior.

For Linux workloads, this is a quick sanity check that the firmware image boots and the UART console configuration is at least self-consistent before FPGA deployment.
