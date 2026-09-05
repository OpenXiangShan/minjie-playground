# XDMA Driver

Build, install, and configure the Xilinx XDMA character-mode driver for FPGA DiffTest.

## Prerequisites

- FPGA host with the board visible on PCIe (`lspci -d 10ee:`)
- Driver source at `dma_ip_drivers/XDMA/linux-kernel/xdma/`
- Kernel headers installed (`/lib/modules/$(uname -r)/build`)

## 1. Build

```bash
cd /path/to/minjie-playground/dma_ip_drivers/XDMA/linux-kernel/xdma
make clean
make DEVICE_ID=0x9048 VENDOR_ID=0x10ee POLLING=1
```

### Build Parameters

| Parameter | Example | Description |
|-----------|---------|-------------|
| `DEVICE_ID` | `0x9048` | XDMA PCIe device ID (check with `lspci -nn -d 10ee:`) |
| `VENDOR_ID` | `0x10ee` | Xilinx vendor ID |
| `POLLING` | `1` | Enable poll mode (avoids interrupt dependency) |
| `c2h_timeout` | (optional) | C2H timeout in milliseconds |
| `h2c_timeout` | (optional) | H2C timeout in milliseconds |

> The device ID depends on the XDMA IP configuration in the bitstream. Use `lspci -nn -d 10ee:` to find the actual ID.

## 2. Install

```bash
sudo make install
```

This copies `xdma-chr.ko` to `/lib/modules/$(uname -r)/xdma/` and runs `depmod`.

Verify:
```bash
modinfo xdma_chr | grep alias
# Should include the configured DEVICE_ID
```

> After a kernel update, rebuild and reinstall the driver.

## 3. Load Script

`/usr/local/bin/load_xdma.sh`:

```bash
#!/bin/bash
set -e

# Unload existing modules
if lsmod | grep -q xdma_chr; then
    /sbin/rmmod xdma_chr
fi
if lsmod | grep -q "^xdma "; then
    /sbin/rmmod xdma
fi

# Load the xdma-chr driver
/sbin/modprobe xdma_chr

# Wait for device nodes. Persistent permissions are provided by the udev rule
# below, including nodes recreated by a PCIe remove/rescan.
sleep 2

echo "XDMA driver loaded. Devices:"
ls /dev/xdma0_* 2>/dev/null || echo "WARNING: no xdma devices found"
```

Install `/etc/udev/rules.d/99-xdma-local.rules` so hot rescans do not require a
separate `sudo chmod`:

```udev
SUBSYSTEM=="xdma", KERNEL=="xdma0_*", MODE="0666"
```

Reload the rule before the next driver bind:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=xdma
```

Install:
```bash
sudo install -m 755 load_xdma.sh /usr/local/bin/load_xdma.sh
```

## 4. systemd Service

`/etc/systemd/system/load-xdma.service`:

```ini
[Unit]
Description=Load XDMA driver (xdma-chr with polling mode)
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/load_xdma.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable load-xdma.service
sudo systemctl start load-xdma.service
```

## 5. Verify

```bash
lsmod | grep xdma_chr
lspci -Dnnk -d 10ee:9048
ls /dev/xdma0_*
# Expected: c2h_0, h2c_0, control, user, xvc, events_0-15
```

`fpga-host` uses `/dev/xdma0_h2c_0` for the default H2C workload load path and `/dev/xdma0_c2h_*` for DiffTest packets from FPGA to host.
If `run_host` fails before printing `XDMA H2C queued`, verify that the H2C node exists and has write permission.

For a DiffTest bitstream, the env-scripts `write_bitstream` flow removes the
endpoint on `$FPGA_HOST` immediately before programming on `$FPGA_RUNTIME` and
always attempts a rescan afterward. The rescan waits for `xdma-chr`, then prints
the endpoint, live PCI configuration value, and recreated device nodes. An
all-`ff` configuration read is treated as a failed rescan even if stale nodes
remain. Run the repository scripts as a normal user; only their internal sysfs
`tee` operations require sudo.

## 6. Troubleshooting

### No device nodes after driver load

Check if the PCIe device is enumerated:
```bash
lspci -d 10ee:
```
If empty, the FPGA may need a bitstream reprogram (see [workflow.md](./workflow.md)).

Check if the device ID matches what the driver was compiled with:
```bash
lspci -nn -d 10ee:       # actual ID
modinfo xdma_chr | grep alias  # driver-supported IDs
```
If mismatched, either rebuild with the correct `DEVICE_ID` or add it at runtime:
```bash
echo "10ee 9048" | sudo tee /sys/bus/pci/drivers/xdma-chr/new_id
```

### Driver loaded but zero references

If `lsmod` shows `xdma_chr` with `0` used-by count and no `/dev/xdma*`, the driver didn't probe any device. This usually means a device ID mismatch — see above.
