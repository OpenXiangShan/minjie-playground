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

2. Verify the device appears on the PCIe bus:

    ```sh
    lspci | grep -i xilinx
    ```

3. If the device is visible but the driver fails, check driver debug logs:

    ```sh
    dmesg | tail -50
    ```

4. Review the Vivado bitstream generation log for synthesis or implementation warnings:

    ```text
    build/build-log/bit-<cpu>-<timestamp>.log
    ```

5. Try removing and rescanning the PCIe device:

    ```sh
    # On the FPGA host:
    sudo env-scripts/fpga_diff/tools/pcie-remove.sh
    sudo env-scripts/fpga_diff/tools/pcie-rescan.sh
    ```

## 2. XDMA Stalls or Packet Errors

**Symptoms**: `fpga-host` hangs after a few seconds; error messages about unexpected packet length or corrupted data; sporadic "DMA timeout" errors.

**Possible Causes**:

| Cause | How to check |
|-------|-------------|
| XDMA internal logic error | Check `package_idx` in the XDMA logic for sequence gaps |
| DiffTest packet framing mismatch | Check the `DIFFTEST_QUERY` output for packet counts and sizes |
| Hardware signal integrity issue | Use ILA (Integrated Logic Analyzer) to capture XDMA transactions |

**Debugging Steps**:

1. **Check packet index continuity**: The XDMA logic maintains a `package_idx` counter. If packets are dropped or reordered, the counter will show gaps. Use ILA or add debug prints to verify.

2. **Enable DIFFTEST_QUERY**: Rebuild the host with query support to get packet-level diagnostics:

    ```sh
    make host xiangshan FPGA_HOST_HOME=$RELEASE_DIR DIFFTEST_QUERY=1
    ```

    Sync and re-run new host to see per-packet statistics.

3. **Use ILA for signal-level debugging**: If software diagnostics are inconclusive, add ILA probes in Vivado to capture:
    - XDMA AXI transactions (address, data, valid/ready)
    - DiffTest packet boundaries and `package_idx`
    - DMA descriptor ring state

    After adding probes, regenerate the bitstream and use the `.ltx` file with Vivado Hardware Manager.

4. **Check for XDMA driver issues**: Review `dmesg` for DMA errors or timeouts. Consider reloading the XDMA driver:

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
| DDR write failure | Confirm `write_jtag_ddr` completed successfully |
| UART configuration mismatch | Check if the workload DTS matches the hardware |

**Debugging Steps**:

1. **Check if packets are being received**: Run `fpga-host` with verbose output or `DIFFTEST_QUERY` mode. If no packets arrive at all, the CPU is likely not running.

2. **Verify the DDR write succeeded**: Re-run `write_jtag_ddr` and check its output for errors. The JTAG write script should report the number of bytes written.

3. **Verify the workload binary**: Check the file size is reasonable:

    ```sh
    ls -la ready-to-run/linux-hello/linux-hello.bin
    ```

    For Linux workloads, the binary should be several megabytes. A very small file suggests a build failure.

4. **Check the reset sequence**: Ensure `reset_cpu` was called after `write_jtag_ddr`:

    ```sh
    make reset_cpu REMOTE=fpga REMOTE_DIR=$FPGA_ROOT FPGA_BIT_HOME=$BIT_ROOT
    ```

5. **Try a simpler workload**: If a Linux workload hangs, try an AM bare-metal test to isolate the issue:

    ```sh
    make workload TARGET=am/hello
    ```

6. **Verify UART configuration**: If the workload boots but produces no serial output, the DTS UART node may not match the hardware. See [workload.md](./workload.md) for UART configuration details.

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
    make nemu NEMU_CONFIG=riscv64-xs-ref-novec-nopmppma_defconfig

    # NutShell
    make nemu NEMU_CONFIG=riscv64-nutshell-ref_defconfig
    ```

    A common mistake is using the XiangShan NEMU config with NutShell, or vice versa.

2. **Check the mismatch details**: The `fpga-host` error output shows the checker name, cycle number, and divergent DUT vs REF state. Note which checker (e.g., `IntWriteback`, `CSR`, `Load`) triggers first — this narrows the scope.

3. **Reproduce in simulation**: If the NEMU config is correct and the mismatch persists, it may be a DiffTest internal issue. Run the same workload in software simulation (EMU/simv) to verify:

    Refer to [`difftest/docs/test.md`](../difftest/docs/test.md) for simulation build and run commands, and [`difftest/docs/workflow.md`](../difftest/docs/workflow.md) for the phased debugging escalation:

    - **Level 1**: Console output — identify the first failing checker and cycle
    - **Level 2**: Query DB — compare DUT and REF state at the divergent step
    - **Level 3**: Waveform dump — if Query DB is not sufficient, dump FST waveforms

4. **Check for known issues**: Some comparison errors are caused by non-deterministic hardware state (e.g., timer CSRs, performance counters). These are typically excluded via `DIFFTEST_EXCLUDE`. Verify the exclude list includes appropriate modules.

## Quick Reference

| Symptom | First check | Likely section |
|---------|-------------|----------------|
| No PCIe device | `lspci`, `dmesg` | [Section 1](#1-xdma--pcie-not-recognized) |
| XDMA timeout or data corruption | `DIFFTEST_QUERY`, `package_idx` | [Section 2](#2-xdma-stalls-or-packet-errors) |
| Host runs but no output | Packet reception, workload `.bin` size | [Section 3](#3-no-output-when-running-host) |
| Comparison mismatch | NEMU config, checker name | [Section 4](#4-packets-received-correctly-but-difftest-comparison-fails) |
