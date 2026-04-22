# Workload Compilation

This document covers workload build options, device tree configuration, and UART/interrupt setup for FPGA DiffTest.

## Build Command

```sh
make workload xiangshan TARGET=<target>   # XiangShan
make workload nutshell  TARGET=<target>   # NutShell
```

The `DESIGN` (xiangshan/nutshell) is required. For AM targets, the Makefile automatically sets:

| Design | ARCH | CPPFLAGS |
|--------|------|----------|
| xiangshan | `riscv64-xs` | `-DUART16550=1` |
| nutshell | `riscv64-nutshell` | `-DUART16550=1` |

`-DUART16550=1` selects the ns16550a serial driver in the AM runtime. Without it, UARTLite is used.

You can override these by setting `AM_CPPFLAGS` explicitly.

Available targets:

| Category | Target | Description |
|----------|--------|-------------|
| Linux | `linux/hello` | Minimal Linux with hello-world init |
| Linux | `linux/coremark` | CoreMark benchmark |
| Linux | `linux/coremark-pro` | CoreMark-Pro benchmark |
| Linux | `linux/rvv-bench` | RISC-V Vector benchmark |
| Linux | `linux/kvmtool` | KVM tool (virtualization) |
| Linux | `linux/litmus-tests-riscv` | Memory model litmus tests |
| AM | `am/hello` | Bare-metal hello world |
| AM | `am/riscv-tests` | RISC-V ISA compliance tests |
| AM | `am/riscv-vector-tests` | RISC-V Vector ISA tests |
| AM | `am/cputest` | AM CPU tests |
| AM | `am/coremark` | Bare-metal CoreMark |
| AM | `am/misc-tests` | Miscellaneous AM tests |

Output for each target:

```text
ready-to-run/<design>-<target-slug>/<design>-<target-slug>.bin    # raw binary image
ready-to-run/<design>-<target-slug>/<design>-<target-slug>.txt    # DDR initialization file (via Bin2ddr)
```

For example, `make workload xiangshan TARGET=am/hello` produces:

```text
ready-to-run/xiangshan-am-hello/xiangshan-am-hello.bin
ready-to-run/xiangshan-am-hello/xiangshan-am-hello.txt
```

## Firmware Assembly

Linux workloads are assembled into a single firmware image containing:

```text
Offset        Component
──────────    ─────────────────
0x0           GCPT bootloader (startup)
+1536 KB      Device tree blob (.dtb)
+1024 KB      OpenSBI (fw_jump)
+2 MB         Linux kernel + initramfs
```

The assembly is performed by `workload-builder/scripts/build-firmware-linux.sh`. Memory base is `0x80000000`.

### Using `xiangshan-fpga-noAIA.dtb`

For Linux workloads in the current flow, the top-level `make workload` splices `xiangshan-fpga-noAIA.dtb` by default. You do not need to pass extra arguments:

```sh
make workload xiangshan TARGET=linux/hello
```

Internally, the flow still does the DTB replacement:

1. Build `workload-builder/build/linux-workloads/hello/fw_payload.bin` and the generated DTBs.
2. Locate `workload-builder/build/linux-workloads/hello/dt/xiangshan-fpga-noAIA.dtb`.
3. Splice that DTB into `ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.bin` at the fixed 1536 KiB DTB offset before running Bin2ddr.

If you need to override the default, pass only the `.dtb` filename under the generated `dt/` directory:

```sh
make workload xiangshan TARGET=linux/hello WORKLOAD_DTB=xiangshan.dtb
```

`WORKLOAD_DTB` is resolved under:

```text
workload-builder/build/linux-workloads/<workload>/dt/<dtb-name>
```

For the current XiangShan FPGA flow, `xiangshan-fpga-noAIA.dts.in` means:

- AIA is not described in the DTS
- Linux uses the legacy CLINT + PLIC interrupt topology
- the FPGA UART16550 is exposed as the Linux console

## Device Tree and UART Configuration

Each platform has a device tree template under `workload-builder/dts/`. The UART type and configuration differ by platform.

### Platform Comparison

| Property | XiangShan (ns16550a) | NutShell (UARTLite) |
|----------|---------------------|---------------------|
| DTS template | `xiangshan.dts.in` | `nutshell.dts.in` |
| Compatible string | `ns16550a` | `xilinx,uartlite` |
| Base address | `0x310b0000` | `0x40600000` |
| Clock frequency | 10 MHz | N/A (fixed baud) |
| Baud rate | Divisor-based | 115200 (hard-coded) |
| Interrupt | PLIC, interrupt #1 | None (polled) |
| `reg-shift` | `0x0` | N/A |
| `reg-io-width` | `0x1` (8-bit) | N/A |
| NEMU config flag | `CONFIG_HAS_UART_SNPS` | `CONFIG_HAS_UARTLITE` |

### ns16550a UART (XiangShan)

The ns16550a node in `xiangshan.dts.in`:

```dts
serial@310b0000 {
    compatible = "ns16550a";
    reg = <0x0 0x310b0000 0x0 0x1000>;
    clock-frequency = <10000000>;
    interrupt-parent = <&PLIC>;
    interrupts = <1>;
    reg-shift = <0x0>;
    reg-io-width = <0x1>;
};
```

**Key properties:**

- **`reg-shift`**: The number of bits to left-shift the register index to obtain the byte address. A value of `0` means registers are at consecutive byte addresses (offset 0, 1, 2, ...). A value of `2` means registers are at 4-byte-aligned addresses (offset 0, 4, 8, ...), which is common on platforms with 32-bit bus access. Change this to match the actual hardware register spacing.

- **`reg-io-width`**: Access width in bytes. `1` for 8-bit MMIO access, `4` for 32-bit. Must match the hardware bus implementation.

- **`interrupt-parent` / `interrupts`**: Routes the UART interrupt through the PLIC. The interrupt number (`1` here) must match the hardware wiring in the RTL. The PLIC node is defined earlier in the DTS:

```dts
PLIC: plic@3c000000 {
    compatible = "riscv,plic0";
    reg = <0x0 0x3c000000 0x0 0x4000000>;
    interrupts-extended = <&cpu0_intc 0xb &cpu0_intc 0x9>;
    /* 0xb = M-mode external interrupt, 0x9 = S-mode external interrupt */
};
```

### UARTLite (NutShell)

The UARTLite node in `nutshell.dts.in`:

```dts
serial@40600000 {
    compatible = "xilinx,uartlite";
    reg = <0x0 0x40600000 0x0 0x10>;
    current-speed = <0x1c200>;
};
```

UARTLite is simpler: no interrupt routing, no clock-frequency, no reg-shift/reg-io-width. It uses firmware-polled I/O.

### Modifying UART Configuration

To change UART settings:

1. **Edit the DTS template** at `workload-builder/dts/<platform>.dts.in`. For example, to change `reg-shift` for a platform with 32-bit register spacing:

    ```dts
    reg-shift = <0x2>;        /* registers at 4-byte intervals */
    reg-io-width = <0x4>;     /* 32-bit MMIO access */
    ```

2. **Rebuild the workload** to regenerate the `.dtb`:

    ```sh
    make workload xiangshan TARGET=linux/hello
    ```

3. **Update NEMU configuration** if the UART model is changed. NEMU selects UART behavior via Kconfig flags in `NEMU/configs/`:
    - `CONFIG_HAS_UART_SNPS=y` — for ns16550a-compatible UART (XiangShan)
    - `CONFIG_HAS_UARTLITE=y` — for Xilinx UARTLite (NutShell)
    - The UART base address is also hardcoded in NEMU config

    If switching between UART types, choose the matching NEMU defconfig:

    ```sh
    # XiangShan (ns16550a)
    make nemu NEMU_CONFIG=riscv64-xs-ref-novec-nopmppma_defconfig

    # NutShell (UARTLite)
    make nemu NEMU_CONFIG=riscv64-nutshell-ref_defconfig
    ```

### Interrupt Routing

The full interrupt path for ns16550a-based platforms:

```text
UART IRQ ──► PLIC ──► CPU interrupt controller
                       (M-mode ext IRQ 0xb / S-mode ext IRQ 0x9)
```

The DTS must declare:

1. A CPU interrupt controller (`riscv,cpu-intc`) for each hart
2. A CLINT for timer/software interrupts
3. A PLIC with `interrupts-extended` wiring to each hart's interrupt controller
4. UART `interrupt-parent` pointing to the PLIC, with the correct interrupt number

If adding a second core, extend the PLIC `interrupts-extended` list. See `spike-2core.dts.in` or `yanqihu-2core.dts.in` for examples.

## NEMU Reference Model

The NEMU SO acts as the golden reference for DiffTest comparison. Each design requires a matching defconfig:

| Design | Default NEMU Config |
|--------|---------------------|
| XiangShan | `riscv64-xs-ref-novec-nopmppma_defconfig` |
| NutShell | `riscv64-nutshell-ref_defconfig` |

Build:

```sh
make nemu NEMU_CONFIG=<defconfig-name>
```

Output: `ready-to-run/<defconfig-name>/riscv64-nemu-interpreter-so`

A mismatch between the NEMU config and the actual hardware UART type will cause DiffTest comparison errors on UART register accesses. Always ensure the NEMU UART config matches the DTS.
