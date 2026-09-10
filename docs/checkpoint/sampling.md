# BBV-only checkpoint sampling

The profiling and checkpoint engines are unchanged. Selection consumes the
existing `simpoint_bbv.gz`; CPI, performance counters, memory addresses, and
microarchitecture models are not inputs. All weights assume equal-length
instruction intervals, following the existing profiling/checkpoint contract.
The sampled population is the intervals actually emitted in the BBV, not an
unrecorded final partial interval or execution outside the profiling region.

## Selection methods

| Method | Selection | Weight per selected interval |
| --- | --- | --- |
| `simpoint` | Existing SimPoint centroid representatives | Original SimPoint weight |
| `random` | Uniform sampling without replacement across all N intervals | 1 / B |
| `bbv-stratified` | SimPoint labels, then uniform sampling without replacement within each stratum | N_h / (N * m_h) |

Here B is the total sample budget, N_h is the number of intervals in stratum h,
and m_h is its allocated sample count. Cluster count and sample count are
separate: `--max-k` bounds the former; `--num-samples` fixes the latter for the
two randomized methods. SimPoint still chooses its actual cluster count.

BBV-stratified allocation gives each nonempty stratum one sample, distributes
the remaining budget in proportion to stratum size, and uses largest remainders
with cluster-ID tie-breaking for integer rounding. A saturated stratum receives
no more samples than it has intervals; excess budget is redistributed. Every
nonempty stratum is retained. The centroid is not forced into the random sample.

For a new run, sampling seed defaults to 42, initialization seed to 100000, and
projection seed to 200000. Vary `--seed` alone to study within-stratum selection
while holding the clustering fixed. Vary `--seedkm` or `--seedproj` separately
to study clustering sensitivity. RNG instances are local to each workload;
thread scheduling does not affect selection. Reproduction assumes identical
BBV, tools, Python implementation/version, and options.

## Full flow

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/demo.bin \
  --archive-id demo-stratified \
  --sampling-method bbv-stratified \
  --max-k 20 --num-samples 60 \
  --seed 42 --seedkm 100000 --seedproj 200000
```

`--max-k 20` is an actual upper bound, including for `xalancbmk`. Defaults remain
30 and 100 respectively when omitted. In stratified mode the bound is also
capped at B so every nonempty stratum can receive at least one sample. A budget
larger than N is rejected, rather than duplicating points or silently reducing B.

The full flow retains existing NEMU/QEMU runtime requirements and produces the
same checkpoint formats. New methods are currently selected via the local CLI;
the existing GitHub workflow continues to expose the baseline flow.

## Compare selectors without generating checkpoints

The direct stage entry does not require a workload binary:

```bash
python3 scripts/checkpoint/step_cluster.py \
  --archive-root /path/to/source-archive --workload demo \
  --sampling-method random --num-samples 60 --seed 42 \
  --output-dir /path/to/experiments/random-60-seed42/demo

python3 scripts/checkpoint/step_cluster.py \
  --archive-root /path/to/source-archive --workload demo \
  --sampling-method bbv-stratified --max-k 20 --num-samples 60 \
  --seed 42 --output-dir /path/to/experiments/stratified-60-seed42/demo
```

The random-only stage requires Python and the BBV file, but no NEMU_HOME,
SimPoint, or numactl. The two SimPoint methods require numactl and the executable
at `$NEMU_HOME/resource/simpoint/simpoint_repo/bin/simpoint`, but do not require a
built NEMU interpreter when invoked only for selection.

For a batch whose original binary directory is still available:

```bash
python3 scripts/checkpoint/generate_checkpoint.py \
  --input-path /path/to/bins --archive-id source-archive \
  --cluster-only --cluster-output-root /path/to/experiments/stratified-seed43 \
  --sampling-method bbv-stratified --max-k 20 --num-samples 60 --seed 43
```

The source archive is resolved using the normal archive root configuration.
Cluster-only never executes profiling, checkpointing, or metadata aggregation.
The experiment root must not already exist; it contains one directory per
workload. Direct stage invocation similarly rejects nonempty output directories.
Use a new directory for each method/seed to retain comparable results.

To generate checkpoints from a chosen configuration, run the normal flow with
those options and `--resume-after profiling` on an archive whose downstream
stages may be replaced. This repeats selection with the recorded seeds; the
cluster-only command itself does not promote or replace a source selection.

## Outputs and weights

- `simpoints0`: `interval_id sample_id` rows; interval IDs remain zero-based BBV
  row indices. Randomized outputs are sorted by interval ID.
- `weights0`: `weight sample_id` rows in exactly the same order as `simpoints0`,
  as required by NEMU's lockstep reader. Each selected point has a unique sample
  ID, even when multiple samples came from the same original cluster.
- `labels0`: SimPoint `cluster_id distance` rows in BBV order, for both
  SimPoint-based methods. Original cluster IDs are retained in provenance.
- `centroid_simpoints0` / `centroid_weights0`: unmodified SimPoint representatives
  before randomized selection, for the stratified mode only.
- `sampling.json`: resolved options, effective maxK, interval/sample counts,
  decompressed-BBV SHA-256, Python version, selector/sampler and SimPoint binary hashes,
  executed command, stratum sizes/allocations, and selected point mappings.
- `cluster.out.log` / `cluster.err.log`: selection logs. Full-flow runs also copy
  these logs to the existing archive log directory.

For a single-interval BBV, all modes select interval 0 with weight 1 directly,
avoiding the old SimPoint single-vector edge case.

Selection outputs are published together only after success. Malformed or empty
BBV rows and label-count mismatches fail explicitly instead of renumbering rows.
The parser accepts the existing standard sparse BBV format, not the optional
NEMU detailed-profiling format containing addresses.

For newly recorded selections, metadata retains every positive weight, including
weights at or below 1e-4. Legacy archives retain their old filtering behavior.
For randomized selections **both `checkpoints_all.json` and the compatibility
`checkpoints_cov0.3.json` contain the full sample set**; truncating to the largest
weights would change the sampling design. For SimPoint the latter remains the
legacy top-weight subset. Each new workload JSON records its sampling options.
External consumers must likewise avoid independently filtering small weights.

Checkpoint resume inherits saved sampling options. Explicit incompatible options
are rejected; use profiling resume or a separate experiment to change selection.
Auto-resume's temporary subset of missing points preserves their original
weights, then restores the complete point/weight files before final metadata.

## Evaluation boundary

Compare methods at equal *actual* sample count and identical measurement/warmup
lengths. A shared maxK does not guarantee equal actual count for SimPoint.
Separately compare within-stratum selection with fixed labels, reporting any
increase in simulation budget.

BBV reconstruction/coverage and seed stability can be evaluated without timing
simulation, but do not prove CPI accuracy. Low-performance regions are genuine
behavior, not outliers to remove. Multiple random samples may capture variation
hidden by identical BBVs, but a small sample can still miss rare slow regions.

For performance evidence, use a preselected independent random validation set
in the existing RTL/FPGA evaluator, report its uncertainty, and hold warmup and
measurement windows constant. Validation CPI is not an input to this selector.
No SPEC CPI accuracy improvement is claimed by this implementation.

## Checks

```bash
python3 -m unittest discover -s scripts/checkpoint/tests -v
```

These checks cover exact bounded allocation, stratum weight conservation,
original interval IDs, malformed inputs, metadata filtering, output protection,
cluster-only operation, and partial checkpoint resume. They do not require a
simulator or a SPEC workload.
