# Audited random-update experiment

**Result: the declared service, setup-inclusive and p99 matrix passes.** This is an experimental custom engine, not a supported RefPot database or a SQLite wrapper. SQLite is only the comparator.

Two complete campaigns produced **672 records**: 2 campaigns × 2 datasets × 4 client counts × 2 SQLite cache budgets × 3 repeats × 7 candidates. Each trial executes 131,072 logical update requests. All 16 campaign/dataset/client cells pass 2× service and setup-inclusive speed; native p99 beats the best-tested SQL p99 in each cell.

- Service speedup: **3.04–5.95×**.
- Including setup and final maintenance: **2.99–5.91×**.
- Full final/reopened rows and atomic request frontiers verified.
- **4–9 checkpoints per trial**, including final maintenance; ring reuse is exercised.
- **Remaining failure:** reopen with full-state validation is slower for native in all 16 cells. This includes the oracle scan, not isolated recovery latency.

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
