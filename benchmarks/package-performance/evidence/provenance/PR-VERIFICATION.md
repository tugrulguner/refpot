# Parent verification: RefPot PRs 20 and 21

## Exact targets

- Baseline main: `6cc633fac687dbdbfab211507b3d87caa5ffcd82`.
- Engine PR21: `e784db03cf797518ec852a19e73202311eabce7f` — https://github.com/tugrulguner/refpot/pull/21
- Harness PR20: `88626e10db9190b77ac0e46c1a3f05dfa5613ace` — https://github.com/tugrulguner/refpot/pull/20
- Conflict-free `git merge-tree` result: `abd14d22730fddfb961cf58f4b73b5816052dbf3`. This is a local tree, not a merge commit or GitHub merge.

## Fixes verified

Engine transactions retain affected rows/deletions rather than full-state map copies; commit records those effects rather than rediscovering them with full-state differencing. Size accounting is incremental. Recovery validates/prepares a frame and applies its effects without copying unrelated rows. Public API and storage framing remain unchanged.

The parent review found and reproduced an acknowledged near-capacity transaction that could not reopen, and net-no-op transactions writing unnecessary WAL. Both failed on the original PR head and pass with the final installed wheel. New fault tests intercept real native allocations, preserve prior valid staged changes after an allocation error, verify preparation refusal leaves WAL unchanged, and count zero post-sync publication allocations. The production wheel contains no test hooks.

The harness review corrected false SQLite pending-WAL labeling, added pilot calibration/frozen counts, persisted raw validation, plan hash sidecars, careful provenance, and rejects NaN/nonpositive speedup thresholds before execution. SQLite ordinary close/reopen is deliberately not labeled equivalent to RefPot pending-WAL replay.

## Parent execution

Built separate baseline and candidate wheels from their literal source heads and installed them into isolated Python 3.14.7 environments. Imports resolved to each environment's site-packages, not an editable checkout. Candidate installed behavioral/recovery/I/O/capacity tests: **35 passed**. Parent's previously failing capacity/no-op probe also passed; production hook absence was asserted.

Exported the conflict-free integration tree without creating a branch merge and ran the complete combined suite against the installed candidate wheel: **96 passed**. The first attempt had 95 passes and one environment failure because this consumer environment lacked declared development dependency PyYAML; after installing that dependency the complete rerun passed. This was not a source fix. Examples exercised by state-machine tests run twice; quickstart was additionally executed twice successfully.

Both PRs' exact-head GitHub check sets were all successful at final performance verification. All independent reviews were incorporated. Final parent verdict: **can merge** for both exact heads, with 26 successful GitHub checks per PR and conflict-free integration. Posted reviews were read back and verified:

- PR20: https://github.com/tugrulguner/refpot/pull/20#pullrequestreview-5497958212
- PR21: https://github.com/tugrulguner/refpot/pull/21#pullrequestreview-5497958331

Nothing was merged or released.

## Measured package performance

Two row counts, three workloads, RefPot plus four SQLite configurations, five repeats, separately for baseline and candidate: **300 unique measured records**. All operation phases met the frozen 20 ms minimum. Each baseline/candidate pair uses identical plan/harness hashes, seed and per-cell operation counts. Final write checkpoint is included. Rows/counts are checked after operations and reopening. SQLite uses actual cached parameterized statements, WAL/FULL, NORMAL/EXCLUSIVE locks, thresholds64/1000; settings are read back. Strongest tested median comparator is used per cell.

| Rows | Workload | Operations | Baseline ms | Candidate ms | Improvement over old RefPot | Candidate / SQLite speedup |
|---:|---|---:|---:|---:|---:|---:|
| 1,000 | point reads | 16,384 | 21.600 | 21.985 | 0.98x | 2.75x |
| 1,000 | singleton updates | 1,024 | 141.796 | 30.117 | 4.71x | 1.23x |
| 1,000 | batch32 updates | 16,384 | 957.276 | 39.698 | 24.11x | 1.20x |
| 10,000 | point reads | 16,384 | 24.086 | 23.964 | 1.01x | 2.60x |
| 10,000 | singleton updates | 1,024 | 1,722.642 | 32.277 | 53.37x | 1.12x |
| 10,000 | batch32 updates | 8,192 | 5,133.725 | 24.840 | 206.67x | 2.20x |

Speedup versus SQLite means SQLite time divided by candidate time. Read time is essentially unchanged between package versions; do not attribute read wins to these write-path fixes. The largest before/after ratios remove pathological whole-database work, not a universal database speed advantage.

Separate warm-filesystem recovery diagnostic: same 10,000-row checkpointed fixture, three repeats, 12 total records, repeated updates to one key, full-state validation outside timing:

| Pending transactions | Old RefPot median ms | Candidate median ms | Improvement |
|---:|---:|---:|---:|
| 128 | 78.794 | 4.546 | 17.33x |
| 1,024 | 607.873 | 5.694 | 106.76x |

All raw keys/counts/plan hashes/medians/ratios were independently recomputed by `verify-pr-evidence.py`. Evidence is preserved in `pr-performance-evidence/`, including every pilot, raw JSONL, copied plan/sidecar, environment metadata, summary and `comparison.json`.

## Boundaries and unfinished ambition

**The overall >2x SQLite target is not achieved.** Singleton updates and the smaller batch cell remain below2x. This is a scoped improvement PR, not completion of the relational-engine performance roadmap.

These are single-host warm-cache public-Python tests, not native-C++ versus native-C qualification. No physical-power-loss or exact syscall-equivalence claim; macOS fullfsync is OFF in SQLite. No sustained repeated 64MiB maintenance-threshold, larger-than-memory, mixed/insert/delete performance, concurrent-client or cross-platform performance campaign. Final checkpoints are included but do not replace sustained maintenance qualification. Baseline/candidate runs are separate, not interleaved at every repeat; hardware/system effects cannot be completely excluded. Recovery comparison runs candidate then baseline, warm filesystem, ordinary close rather than crash; it is RefPot-only, not a SQLite recovery ratio.

Do not combine these ratios with the earlier review's screen: this final harness retains returned read rows, uses different fixtures/counts, and has a frozen calibration protocol. The two engine versions above were compared using the exact same final harness.
