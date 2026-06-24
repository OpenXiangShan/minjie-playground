# XiangShan Prefetch Analysis Report Guide

This guide instructs an agent to analyze XiangShan prefetcher-related performance counters. The report should determine how a prefetch change affects IPC, demand misses, hit coverage, prefetch timeliness, useless prefetches, dropped requests, and downstream cache/memory pressure.

For the `simulator_err.txt` format, refer to `base-simanalysis-en.md`.

## Prefetcher Overview

The current XiangShan prefetcher library and default prefetch architecture are shown below. During analysis, use the actual tested configuration and the counters present in the log as the source of truth.

| Prefetcher | Training location | Prefetch location | Default status |
| --- | --- | --- | --- |
| Stream | L1 | L1, L2 | Enabled |
| Stride | L1 | L1, L2 | Enabled |
| Berti | L1 | L1, L2 | Disabled |
| SMS | L1 | L1, L2 | Enabled |
| VBOP | L2 | L2 | Enabled |
| PBOP | L2 | L2 | Enabled |
| TP | L2 | L2 | Enabled |
| NextLine | L2 | L2 | Disabled |

## Important Counter Semantics

In counter names, `?` represents the cache level, such as `l1` or `l2`; `X` represents a specific prefetcher name, such as `Stream`, `Stride`, or `SMS`.

| Counter name | Meaning | Main use |
| --- | --- | --- |
| `l?prefetchSent` | Total number of prefetch requests sent | Measure prefetch traffic |
| `l?prefetchHit` | Total number of demand requests that hit prefetched blocks | Measure the total number of demand misses reduced by prefetching |
| `l?demandMiss` | Total number of demand requests that missed in the cache | Represent real demand-side cache misses |
| `l?prefetchSentX` | Number of prefetch requests sent by prefetcher X | Measure traffic from one prefetcher |
| `l?prefetchHitX` | Demand requests that hit blocks brought by prefetcher X | Calculate accuracy and coverage for one prefetcher |
| `l?prefetchHitInCacheX` | Demand requests that hit, in cache, blocks brought by prefetcher X | Determine whether prefetched data reached the cache in time |
| `l?prefetchHitInMSHRX` | Demand requests that hit an existing MSHR entry created by prefetcher X | Determine whether prefetching was late but still overlapped with demand |
| `l?prefetchLateX` | Prefetch requests from X that hit an existing data block or MSHR entry | Measure late or duplicate prefetches |
| `l?prefetchLateInCacheX` | Prefetch requests from X that hit an existing block in cache | Measure duplicate prefetches to already cached data |
| `l?prefetchLateInMSHRX` | Prefetch requests from X that hit an existing MSHR entry | Measure overlap with existing misses |
| `l?prefetchLateInCacheX_HitY` | Requests from prefetcher X that hit blocks already brought by prefetcher Y in cache | Analyze overlap or duplication between prefetchers |
| `l?prefetchLateInMSHRX_HitY` | Requests from prefetcher X that hit MSHR entries already created by prefetcher Y | Analyze MSHR-level duplication between prefetchers |
| `l?prefetchUselessX` | Blocks brought by prefetcher X that were evicted before being used by demand | Measure useless prefetches and pollution risk |
| `l?prefetchDropByNackX` | Requests from prefetcher X dropped because of resource pressure or nack | Measure resource pressure and bandwidth contention |

## Core Metrics

Using L1 Stream as an example:

```text
sent = l1prefetchSentStream
accuracy = l1prefetchHitStream / l1prefetchSentStream
coverage = l1prefetchHitStream / (l1prefetchHit + l1demandMiss)
lateRate = l1prefetchLateStream / l1prefetchSentStream
uselessRate = l1prefetchUselessStream / l1prefetchSentStream
dropRate = l1prefetchDropByNackStream / l1prefetchSentStream
```

General rules:

1. If the denominator is 0, output `N/A`.
2. Higher accuracy does not necessarily mean better performance. Also check coverage, demand misses, late, useless, drop, and IPC.
3. Higher sent count may improve coverage, but it may also increase cache/memory pressure.
4. Higher useless count usually indicates pollution risk, but it must be judged together with demand misses and replacement-related counters.
5. Higher late count may mean prefetching is too late, or it may mean demand and prefetch overlap on the same miss. Use `HitInCache` and `HitInMSHR` to distinguish these cases.

## Basic Analysis Workflow

### 1. Start With Top-Level Impact

Compare IPC, cycles, and committed instructions first to determine whether the prefetch change corresponds to a visible performance change. If IPC does not change significantly, report prefetch behavior changes if needed, but do not overstate them as a performance root cause.

### 2. Summarize L1 And L2 Separately

For L1 and L2, summarize the following metrics for each prefetcher:

| Metric | Meaning |
| --- | --- |
| demandMiss | Number of real demand-side misses |
| sent | Number of prefetch requests sent |
| accuracy | Ratio of prefetch requests used by demand |
| coverage | Ratio of prefetch hits over demand misses plus prefetch hits |
| lateRate | Ratio of late or duplicate prefetches |
| uselessRate | Ratio of blocks evicted before being used |
| dropRate | Ratio of requests dropped because of nack or insufficient resources |

In comparison reports, provide at least base/new/delta/delta% and explain the direction of each change.

### 3. Diagnose Benefit Or Regression

Use the following evidence chains first:

| Symptom | Likely judgment | Additional confirmation needed |
| --- | --- | --- |
| demandMiss decreases, coverage increases, and useless/drop does not increase significantly | Prefetching is more effective | Check whether downstream bandwidth worsened |
| accuracy increases but coverage decreases | Prefetching became more conservative and coverage is insufficient | Check whether sent decreased and demandMiss increased |
| sent increases significantly and useless/drop also increases | Prefetching is too aggressive or resource contention increased | Check cache miss, MSHR full, memory bandwidth |
| lateRate increases and IPC decreases | Prefetch timing is late or miss overlap is insufficient | Distinguish late in cache from late in MSHR |
| dropRate increases | MSHR, queue, or downstream resource pressure increased | Check nack, MSHR full, bank conflict |

### 4. Include Downstream Pressure

Prefetch conclusions must check downstream cache/memory pressure. Prioritize:

```text
L1/L2 demand miss MPKI
L1/L2 prefetch traffic per kilo instr
MSHR full cycle ratio
nack/drop count
bank conflict count
memory request bandwidth
replay MPKI
```

If prefetch metrics improve but IPC decreases, first suspect bandwidth contention, cache pollution, MSHR occupancy, or a backend bottleneck masking the benefit.

## Output Requirements

A prefetch analysis report must include at least:

1. Top-level IPC, cycles, and committed instructions.
2. L1 and L2 summaries for demandMiss, prefetchHit, and prefetchSent.
3. accuracy, coverage, lateRate, uselessRate, and dropRate for each prefetcher.
4. Changes in downstream cache/memory pressure.
5. A clear conclusion: benefit, regression, no visible impact, or insufficient evidence.
6. If evidence is insufficient, list missing counters and the next directions to check.
