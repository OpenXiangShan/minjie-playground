# Troubleshooting

Common issues encountered during FPGA DiffTest and how to diagnose them.

## 1. XDMA / PCIe Not Recognized

**Symptoms**: `lspci` does not show the XDMA device; `write_bitstream` or `run_host` fails with "no device found"; the XDMA character devices (`/dev/xdma0_*`) do not appear.

**Possible Causes**:

| Cause | How to check |
|-------|-------------|
| Physical wiring or connection issue | Inspect the PCIe cable and FPGA board LEDs. Verify the FPGA is powered and the PCIe link LED is on. |
| `env-scripts/fpga_diff` wiring mismatch | Review the Vivado project constraints (`.xdc` files under `env-scripts/fpga_diff/constr/`). Ensure the PCIe lane assignments match the physical board. |
| Vivado version incompatibility | Check `env-scripts/fpga_diff/src/tcl/common/check_version.tcl` for supported versions. Run `vivado -version` on the build host. Review the bitstream generation log for warnings. |
| XDMA driver not loaded or version mismatch | Check `dmesg \| grep xdma` for driver load errors. Verify the driver module is installed: `lsmod \| grep xdma`. |

**Debugging Steps**:

1. Check system logs for PCIe enumeration:

    ```sh
    dmesg | grep -i "pci\|xdma"
    ```

2. Verify the configured XDMA device appears on the PCIe bus:

    ```sh
    lspci -Dnnk -d 10ee:9048
    ```

3. If the device is visible but the driver fails, check driver debug logs:

    ```sh
    dmesg | tail -50
    ```

4. Review the Vivado bitstream generation log for synthesis or implementation warnings:

    ```text
    build/build-log/bit-<cpu>-<timestamp>.log
    ```

5. Remove and rescan the PCIe device after every UVHS runtime download:

    ```sh
    # On the FPGA host:
    env-scripts/fpga_diff/tools/pcie-remove.sh
    env-scripts/fpga_diff/tools/pcie-rescan.sh
    ```

    Run the scripts as the normal user. They use narrowly authorized
    `sudo tee` operations for driver unbind, device removal, and bus rescan.
    The remove script prints any active `fpga-host` process and refuses to
    disrupt it. The rescan script waits for `xdma-chr`, prints the endpoint and
    `/dev/xdma0_*` nodes, and checks that the current user can read and write
    the required H2C, C2H, and user nodes. With the documented udev rule, a
    separate `sudo chmod` after rescan is not required.

## 2. XDMA Stalls or Packet Errors

**Symptoms**: `fpga-host` exits before H2C, reports `XDMA H2C write failed:
Connection timed out`, waits after `XDMA H2C queued`, or reports unexpected
packet length/corrupted C2H data.

**Possible Causes**:

| Cause | How to check |
|-------|-------------|
| XDMA internal logic error | Check `package_idx` in the XDMA logic for sequence gaps |
| DiffTest packet framing mismatch | Check the `DIFFTEST_QUERY` output for packet counts and sizes |
| Hardware signal integrity issue | Use ILA (Integrated Logic Analyzer) to capture XDMA transactions |

**Debugging Steps**:

1. **Classify the failing stage**:

    | Last host marker | Interpretation |
    |------------------|----------------|
    | Cannot open `/dev/xdma0_*` | Enumeration, driver binding, or node-permission failure |
    | `H2C workload size` then `Connection timed out` | XDMA is open, but the FPGA-side H2C path is not accepting the transfer |
    | `XDMA H2C queued` without `H2C load done` | Host DMA submission returned, but the FPGA memory controller did not report completion |
    | `H2C load done` without UART or C2H packets | H2C completed; inspect flash, CPU reset/execution, DDR reads, and C2H instead |

2. **Check packet index continuity**: The XDMA logic maintains a `package_idx` counter. If packets are dropped or reordered, the counter will show gaps. Use ILA or add debug prints to verify.

3. **Enable DIFFTEST_QUERY**: Rebuild the host with query support to get packet-level diagnostics:

    ```sh
    make host xiangshan FPGA_HOST_HOME=$RELEASE_DIR DIFFTEST_QUERY=1
    ```

    Sync and re-run new host to see per-packet statistics.

4. **Use ILA for signal-level debugging**: If software diagnostics are inconclusive, add ILA probes in Vivado to capture:
    - XDMA AXI transactions (address, data, valid/ready)
    - DiffTest packet boundaries and `package_idx`
    - DMA descriptor ring state

    After adding probes, regenerate the bitstream and use the `.ltx` file with Vivado Hardware Manager.

5. **Check for XDMA driver issues**: Review `dmesg` for DMA errors or timeouts. Consider reloading the XDMA driver:

    ```sh
    sudo rmmod xdma
    sudo modprobe xdma
    ```

## 3. No Output When Running Host

**Symptoms**: `fpga-host` starts but produces no console output; no DiffTest comparison messages appear; the process appears to hang.

**Possible Causes**:

| Cause | How to check |
|-------|-------------|
| CPU is stuck (not executing) | Check if XDMA packets are being received at all |
| Workload build issue | Verify the `.bin` file size and content are correct |
| DDR write / reset sequence issue | Confirm which execution path you are using and verify the DDR load and reset steps in that path |
| UART configuration mismatch | Check if the workload DTS matches the hardware |

**Debugging Steps**:

1. **Check which path you are using**:
   Host path: `make run_host ...`
   UART/manual path: `stty -F /dev/ttyUSB0 ...` plus `write_flash -> halt_soc -> write_ddr -> reset_cpu`

   The default host path uses H2C for workload DDR loading only. H2C selects
   its own DDR AXI source ahead of the CPU source and does not need a separate
   `halt_soc` command.
   If the design boots from flash, write the boot image through the env-scripts
   `write_flash` target after each `write_bitstream` and before `run_host`.

2. **If you are using the host path, verify the H2C load step succeeded**:
   Check the `run_host` log for `XDMA H2C queued` and `H2C load done`.
   Also verify that `/dev/xdma0_h2c_0` exists and that the host was built with `USE_XDMA_H2C=1`.
   If the host was intentionally built with `USE_XDMA_H2C=0`, check the log for the `external DDR load command` instead.

3. **Check the write operation's reset ownership**: `write_flash` protects and
   restores CPU execution internally. UVHS `write_ddr` and the manual Vivado
   JTAG DDR flow require the CPU to remain halted until `reset_cpu`. H2C manages
   CPU DDR ownership through the FPGA memory controller instead.

4. **If you are using the UART/manual path, verify the order**:
    Keep the UART terminal open, write the external-LLC flash image when needed,
    then run `halt_soc`, `write_ddr`, and `reset_cpu` in that order.
    `write_flash` takes a raw boot image and must be repeated after every
    `write_bitstream` for an external-LLC design.
    If you skip `halt_soc` or reset too early, the CPU may run before DDR is fully initialized.

5. **Verify the workload binary**: Check the file size is reasonable:

    ```sh
    ls -la ready-to-run/xiangshan-linux-hello/xiangshan-linux-hello.bin
    ```

    For Linux workloads, the binary should be several megabytes. A very small file suggests a build failure.

6. **Check the reset sequence**:
    `write_bitstream` initializes and releases the design. After that:
    Host path: `fpga-host` random-initializes DDR if requested, then loads the workload through H2C, then releases CPU reset.
    UART/manual path: a second `reset_cpu` should be called after `halt_soc`, any boot-flash write, and `write_ddr`:

    ```sh
    make reset_cpu REMOTE=fpga REMOTE_DIR=$FPGA_ROOT FPGA_BIT_HOME=$BIT_ROOT
    ```

7. **Try a simpler workload**: If a Linux workload hangs, try an AM bare-metal test to isolate the issue:

    ```sh
    make workload TARGET=am/hello
    ```

8. **Verify UART configuration**: If the workload boots but produces no serial output on the manual UART path, the DTS UART node may not match the hardware. See [workload.md](./workload.md) for UART configuration details.

9. **For Linux workloads, account for DDR outside the image**:
    Linux can read physical memory beyond the exact bytes in the workload image.
    The bitstream defaults to the 16GB two-rank DDR configuration. `RAM_SIZE=16GB` is now the default for XiangShan `fpga-host` and NEMU runtime initialization; NutShell retains `2GB`. Set it deliberately to match the workload's intended RAM size.
    Prefer `RANDOM_MEM=1` and `SEED=1234` for deterministic initialization.
    If random DDR initialization is disabled, pad the workload image so every region Linux may access has deterministic contents.

## 4. Packets Received Correctly but DiffTest Comparison Fails

**Symptoms**: `fpga-host` receives data and runs comparison, but reports mismatches between DUT (FPGA) and REF (NEMU) state.

**Possible Causes**:

| Cause | How to check |
|-------|-------------|
| NEMU config mismatch | Verify the NEMU defconfig matches the design |
| NEMU build is stale | Rebuild NEMU after any config change |
| DiffTest internal error | Run simulation-based DiffTest to reproduce |

**Debugging Steps**:

1. **Verify NEMU configuration**: Ensure the NEMU defconfig matches the design:

    ```sh
    # XiangShan
    make nemu NEMU_CONFIG=riscv64-xs-ref_defconfig

    # NutShell
    make nemu NEMU_CONFIG=riscv64-nutshell-ref_defconfig
    ```

    A common mistake is using the XiangShan NEMU config with NutShell, or vice versa.
    XiangShan defaults to the vector-capable `riscv64-xs-ref_defconfig`; use a no-vector NEMU config only with a matching no-vector RTL build.

2. **Check the mismatch details**: The `fpga-host` error output shows the checker name, cycle number, and divergent DUT vs REF state. Note which checker (e.g., `IntWriteback`, `CSR`, `Load`) triggers first — this narrows the scope.

3. **Reproduce in simulation**: If the NEMU config is correct and the mismatch persists, it may be a DiffTest internal issue. Run the same workload in software simulation (EMU/simv) to verify:

    Refer to [`difftest/docs/test.md`](../../difftest/docs/test.md) for simulation build and run commands, and [`difftest/docs/workflow.md`](../../difftest/docs/workflow.md) for the phased debugging escalation:

    - **Level 1**: Console output — identify the first failing checker and cycle
    - **Level 2**: Query DB — compare DUT and REF state at the divergent step
    - **Level 3**: Waveform dump — if Query DB is not sufficient, dump waveforms with ILA

4. **Check for known issues**: Some comparison errors are caused by non-deterministic hardware state (e.g., timer CSRs, performance counters). These are typically excluded via `DIFFTEST_EXCLUDE`. Verify the exclude list includes appropriate modules. Do not exclude `Vec` unless the RTL and NEMU reference are both built for a no-vector flow.

## Quick Reference

| Symptom | First check | Likely section |
|---------|-------------|----------------|
| No PCIe device | `lspci`, `dmesg` | [Section 1](#1-xdma--pcie-not-recognized) |
| XDMA timeout or data corruption | `DIFFTEST_QUERY`, `package_idx` | [Section 2](#2-xdma-stalls-or-packet-errors) |
| Host runs but no output | Packet reception, workload `.bin` size | [Section 3](#3-no-output-when-running-host) |
| Comparison mismatch | NEMU config, checker name | [Section 4](#4-packets-received-correctly-but-difftest-comparison-fails) |
