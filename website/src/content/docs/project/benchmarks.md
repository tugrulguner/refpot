---
title: Historical benchmark results
description: Canonical RefPot guidance and evidence with explicit scope.
---

**This is historical prototype evidence, not a benchmark of the published Python package.** RefPot's current package performance remains unqualified. The experimental alpha has CRUD and transactions; the measured prototype below used a different fixed-schema update path. Do not transfer its ratios or storage guarantees to the package.

## Read the chart correctly

Service and setup-inclusive ratios compare best-tested SQLite time with native prototype time under the experiment's matched policy. A ratio above one favors the prototype. The two campaigns are retained separately; the 2× line is the scoped acceptance threshold, not a universal database guarantee. The chart's reopen failure includes a full-state oracle scan, not isolated recovery latency.

All 16 service/setup/p99 cells passed in this experiment, but reopen and full-state validation lost every cell. Read the full per-cell values and fairness contract below before citing a ratio. Earlier failed experiments are retained rather than discarded. Linux ARM64 Docker/ext4 VM measurements do not establish native macOS, Linux x86_64, bare-metal, Python-binding, ORM, or physical power-loss performance.

## Evidence index

- [Frozen experimental source and original report](https://github.com/tugrulguner/refpot/tree/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates)
- [Independent read-only audit](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/AUDIT.md)
- [Raw records archive](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/data/raw-records.tar.gz)
- [Source and evidence hash manifest](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/manifest.json)
- [Complete analyzer output](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/summary.json)
- [All reopen comparisons](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/recovery-comparison.json)
- [Prior failed experiments](https://github.com/tugrulguner/refpot/tree/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/prior-results)
- [Reproduction tool](https://github.com/tugrulguner/refpot/blob/55c6f6efdee908068dde037e4f74aebac6522349/benchmarks/random-updates/reproduce.py)

## Verify evidence versus rerunning measurements

From a repository checkout, the offline `verify` command below checks the retained hashes, recomputes all 672 raw records and validates the declared matrix. It does **not** execute a new performance campaign or qualify the public package.

The Docker `smoke` command executes actual native and SQLite operations with reopen checks, but its timings are not a complete comparison. The full `campaign` is an explicit expensive opt-in, around ten hours on the recorded machine; it downloads SQLite and uses Docker. Do not run it automatically as part of trying the package. New measurements with a mutable toolchain image are a new experiment, not an exact replay of the old environment.

For future package measurements, use the [performance qualification method](https://refpot.modepot.io/performance-method/). For actual supported operations and failure boundaries, read the [package contract](https://refpot.modepot.io/package-contract/) and [errors and ownership guide](https://refpot.modepot.io/build/errors/).

## Retained experimental report

**Result: the declared service, setup-inclusive and p99 matrix passes.** This is an experimental custom engine, not a supported RefPot database or a SQLite wrapper. SQLite is only the comparator.

Two complete campaigns produced **672 records**: 2 campaigns × 2 datasets × 4 client counts × 2 SQLite cache budgets × 3 repeats × 7 candidates. Each trial executes 131,072 logical update requests. All 16 campaign/dataset/client cells pass 2× service and setup-inclusive speed; native p99 beats the best-tested SQL p99 in each cell.

- Service speedup: **3.04–5.95×**.
- Including setup and final maintenance: **2.99–5.91×**.
- Full final/reopened rows and atomic request frontiers verified.
- **4–9 checkpoints per trial**, including final maintenance; ring reuse is exercised.
- **Remaining failure:** reopen with full-state validation is slower for native in all 16 cells. This includes the oracle scan, not isolated recovery latency.

## Visual summary

![Audited RefPot random-update result: both campaigns, with limitations](/refpot-benchmark.png)

[Full-size PNG](/refpot-benchmark.png) · [Editable SVG](/refpot-benchmark.svg)

The chart shows both campaigns separately, with the 2× target and the recovery failure visible. All values below and in `summary.json` are the accessible text equivalent.

## Full results

Ratios are best-tested SQLite time / native time. The two numbers on each line are campaigns 1 and 2; no averaging away a campaign.

- **100,000 rows / 1 clients:** service 3.833× / 5.953×; setup-inclusive 3.794× / 5.906×.
- **100,000 rows / 4 clients:** service 3.353× / 5.382×; setup-inclusive 3.323× / 5.348×.
- **100,000 rows / 16 clients:** service 4.350× / 4.817×; setup-inclusive 4.289× / 4.752×.
- **100,000 rows / 64 clients:** service 3.037× / 3.920×; setup-inclusive 2.988× / 3.770×.
- **1,000,000 rows / 1 clients:** service 5.357× / 5.040×; setup-inclusive 5.211× / 4.951×.
- **1,000,000 rows / 4 clients:** service 4.907× / 5.277×; setup-inclusive 4.755× / 5.153×.
- **1,000,000 rows / 16 clients:** service 4.994× / 5.290×; setup-inclusive 4.661× / 4.994×.
- **1,000,000 rows / 64 clients:** service 5.028× / 3.378×; setup-inclusive 4.507× / 3.308×.

## Frozen contract and fairness

Fixed rows contain a 64-bit key/value and fixed text. Non-affine keys are `3*i+1+(i%7==0)`. SplitMix64 maps sequential request identities to existing row indexes; requests can revisit keys. Each update adds one and persists an atomic receipt frontier. Full tuples and the frontier are checked before close and after reopen.

Singletons execute directly, one synchronized physical transaction per logical request. Multiple clients submit one outstanding request each to a single writer which drains work already queued, with **no artificial batching delay**. SQLite uses the same queue/coalescing policy, real prepared updates and a receipt-frontier update in the same `BEGIN IMMEDIATE` transaction. This is **not an ordinary update-only SQLite baseline**.

SQLite 3.51.0 uses WAL/FULL, actual cache budgets 2,000 KiB and 131,072 KiB (read back), and autocheckpoint thresholds 64/128/256/512/1024. A serial-128 control is also retained and eligible for singleton comparisons. Cache budgets are not whole-process memory limits. The analyzer selects the fastest three-repeat SQLite median per cell across eligible configurations; native pools six trials (both cache-tag controls). Candidate order rotates; dataset/client/cache order reverses in campaign 2. Service is commit plus final maintenance; setup-inclusive timing runs from backend construction through final maintenance. Validation/reopen are separately timed.

The custom prototype persists an immutable row image plus current-value COW banks, redundant redo copies, checksummed/versioned metadata and an atomic frontier. Packed writes use an `O_DSYNC` descriptor verified with `F_GETFL`; publication follows successful full synchronous-write completion. Ring slots are `32768/MAX_GROUP`, frames are 128/256/512/2048 bytes for groups 1/4/16/64, and dirty partitions number 4,096. This is explicit per-cell experimental geometry, not an automatic public tuning policy.

## Environment and source identity

Measured on macOS Docker Desktop's **Linux ARM64 VM**, using a local Docker named volume whose mountinfo identified **ext4**, Linux 6.10.14-linuxkit and GCC 14.4.0. The recorded result is not bare-metal Linux or native macOS performance. `gcc:14` is a mutable reproduction tag; new toolchain/environment results are distinct experiments, not an exact environment replay. SQLite is fetched from its official 3.51.0 amalgamation and source hashes are checked.

`manifest.json` hashes the retained source and evidence. C++ source and measured raw records are copied from the audited campaign without substitutions. `summary.json` preserves the original analyzer output, including its inherited shorthand scope string; **this document and actual matrix/geometry fields define the precise scope**, not that stale shorthand. No database images or compiled binaries are included.

## Reproduce without a ten-hour surprise

```sh
# No Docker or network: check source/evidence hashes and recompute all 672 records.
python3 benchmarks/random-updates/reproduce.py verify

# Requires Docker and downloads hash-verified official SQLite: actual native/SQLite smoke.
python3 benchmarks/random-updates/reproduce.py smoke

# Expensive opt-in only: 672 sequential trials, about 10 hours on the measured machine.
python3 benchmarks/random-updates/reproduce.py campaign --output /absolute/path/to/new-results
```

The smoke verifies real operations and reopen; it is not a replacement performance campaign. The full campaign uses a fresh Docker volume and read-only source mounts. It does not clean up retained evidence automatically. `check-low.cpp` contains the bounded interruption/corruption/reopen corpus; the measured campaign ran all four configurations under ASan/UBSan before timing. Process exits, corruption and syscall-error tests are **not physical power-loss validation**. Correlated destruction of both redo copies is unsupported.

## Retained misses and acceptance boundaries

Earlier stride-pattern and smaller-horizon experiments missed 2× and/or p99; their summaries are retained in `prior-results/`. SQLite timings varied substantially. Do not combine isolated wins into a universal database claim, infer a physical-device cause, or discard earlier misses. Larger rings repeatedly improved the tested p99, but native throughput sometimes regressed in a paired campaign.

No arbitrary insert/delete/key/text mutation, SQL frontend, constraints, rollback/abort isolation, concurrent readers, Python binding, ORM, physical power-loss guarantee, complete memory/disk resource gate, or supported release is established. **Roadmap product milestones remain unchecked.**

An independent read-only audit verified the exact 672-key matrix, operation equivalence, receipt semantics, timing/maintenance, strongest eligible SQL comparisons, pooled medians and all 16 reopen misses. The audit is documented in `AUDIT.md`; it does not replace missing product qualification.

[Download this page as Markdown](/docs/project-benchmarks.md)
