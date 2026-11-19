# FPGA Host Setup

This page records the host-side checks that should be captured before comparing
FPGA DiffTest runtime performance.

## CPU Performance Mode

FPGA DiffTest throughput can be limited by the host CPU when NEMU or the
DiffTest parser is on the critical path. Before collecting performance numbers,
make sure the FPGA host is not left in a power-saving profile. Use a
performance-oriented CPU profile for benchmark and regression runs.

Record the current state in the run log:

```bash
powerprofilesctl get
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor | sort -u
cat /sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference | sort -u
cat /sys/devices/system/cpu/cpu*/power/energy_perf_bias | sort -u
cat /sys/devices/system/cpu/intel_pstate/no_turbo
```

Expected state on an `intel_pstate` host:

```text
powerprofilesctl get                         -> performance
energy_performance_preference                -> performance
energy_perf_bias                             -> 0
intel_pstate/no_turbo                        -> 0
```

With `intel_pstate`, `scaling_governor` can still show `powersave` while the
effective energy preference is `performance`. In that case, use the EPP/EPB
values above to decide whether the CPU policy is performance-oriented.

For a quick load-side sanity check:

```bash
cpupower frequency-info
```

The important point is not that idle cores stay at a high frequency, but that
the host is allowed to boost under load.

## Perf Hotspot Sampling

Use `perf` when the run needs function-level hotspots for NEMU, DiffTest batch
handling, host memory initialization, or XDMA polling.

Check that `perf` is available and that the kernel policy permits sampling:

```bash
which perf
perf --version
cat /proc/sys/kernel/perf_event_paranoid
```

If `perf_event_paranoid` is too strict, `perf record` will report that
performance monitoring is limited. In that case, adjust host policy before
collecting hotspot data.

Example command shape:

```bash
perf record -F 99 -g -o perf.data -- \
  /path/to/fpga-host \
  --diff /path/to/riscv64-nemu-interpreter-so \
  --ram-size 2GB \
  --random-mem \
  --seed 1 \
  -i /path/to/workload.bin
```

Report command shape:

```bash
perf report -i perf.data --stdio --sort comm,dso,symbol
```

Keep the exact `fpga-host` and NEMU `.so` used by the run so that symbols can
be resolved during report generation.

## Runtime Checks

For comparable FPGA DiffTest throughput measurements, record the host, NEMU,
and workload hashes:

```bash
sha256sum /path/to/fpga-host /path/to/riscv64-nemu-interpreter-so /path/to/workload.bin
```

In the final DiffTest output, compare:

```text
Run time
Simulation speed: <MHz>, <MIPS>
v_difftest_Batch calls/s
DIFFSTATE_SUM calls/s
HOST_TIME elapsed/user/sys
```

The `v_difftest_Batch` and `DIFFSTATE_SUM` rates are useful when a change is
expected to improve NEMU/DiffTest processing rather than FPGA execution itself.

## XDMA Driver

The host also needs the XDMA character driver and `/dev/xdma0_*` nodes for H2C
workload loading and C2H DiffTest packets. See [xdma.md](./xdma.md) for driver
build, install, load service, and troubleshooting.
