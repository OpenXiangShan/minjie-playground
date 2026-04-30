# MinJie Playground

MinJie Playground developed by [XiangShan team](https://github.com/OpenXiangShan).

## Documentation

| Flow | Doc Index |
|------|------|
| Fpga Difftest | [docs/FpgaDiff](docs/FpgaDiff/README.md) |

For shared VU19P access, use [`scripts/fpga_usage.sh`](scripts/fpga_usage.sh) via the top-level `make fpga_init`, `make fpga_status`, `make fpga_claim`, and `make fpga_release` targets. The standard FPGA entry points (`write_bitstream`, `write_jtag_ddr`, `reset_cpu`, `run_host`) now enforce the same occupancy marker under `~/.fpga_used/`.

## LICENSE
Copyright © 2020-2026 Institute of Computing Technology, Chinese Academy of Sciences.

Copyright © 2021-2026 Beijing Institute of Open Source Chip

MinJie-playground is licensed under [Mulan PSL v2](LICENSE).
