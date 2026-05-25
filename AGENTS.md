# MinJie-playground Guidelines

Before doing anything in this repository, read [README.md](README.md) and [docs/README.md](docs/README.md).

For VU19P board access, use the shared status script [`scripts/fpga_usage.sh`](scripts/fpga_usage.sh). Before `write_bitstream`, `write_jtag_ddr`, `reset_cpu`, or `run_host`, check or acquire the lock with the top-level `make fpga_status/fpga_claim` targets if the workflow is not already doing it for you. When work is complete, release it with `make fpga_release` so `~/.fpga_used/` is updated back to idle.
