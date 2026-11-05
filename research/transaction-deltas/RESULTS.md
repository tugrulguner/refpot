# Transaction-local propagation and absence: bounded findings

Candidate source: `283f96dc06a23184c1ba85faf408449becaa07a5`. Locally built wheel/sdist metadata remains `0.1.2`; these are not published-package measurements. Native headers and installed extension/archive hashes are retained in `evidence/qualified.json`.

## Correctness

Wheel and separately built sdist consumers each passed 58 tests / 34 subtests outside the checkout. Both examples ran twice. The inherited full-state replay passed 24 transactions per engine; the new absence-aware replay passed 11 per engine. SQLite, overlay and modular histories matched after every represented statement and transaction. A seeded API test additionally checks both input bags and downstream groups over 40 eight-statement transactions per mode. Allocation refusal and native publication tests passed in normal and ASan/UBSan builds. These are bounded tests, not universal correctness, durability or concurrency qualification.

## Service and memory screen

18 fresh-process records: three repeats × two workloads × three engines, 256 rows per source. Setup and validation are outside service timing; service includes BEGIN, updates, commit/assertion checking and candidate reclamation. Setup, final verification and close are separately recorded. Sparse updates one row; dense updates half the rows twice, cancelling the changes. SQLite caches prepared statements and maintains groups with indexed triggers. Native SQL parses each call. Both are volatile.

| Engine | Workload | Median service µs | Median setup µs | Median process peak RSS bytes |
| --- | --- | ---: | ---: | ---: |
| sqlite | sparse | 96.041 | 1528.875 | 31342592 |
| sqlite | dense | 925.291 | 1557.000 | 31440896 |
| native-overlay | sparse | 59.125 | 4470.875 | 31588352 |
| native-overlay | dense | 6078.250 | 3961.250 | 31506432 |
| native-modular | sparse | 206.625 | 10028.584 | 31686656 |
| native-modular | dense | 5124.625 | 9642.167 | 31555584 |

The overlay sparse median is lower than this SQLite control, but modular sparse and both dense cells are slower. The transactions are short and the repeat count small: these are screening observations, not speed claims. Both native modes have higher setup medians here. RSS is the whole Python process high-water mark including setup/imports, not isolated engine memory, allocation volume or a live-memory delta. Similar RSS does not prove similar engine allocation cost.

## What changed and what remains

Successive appends propagate only new statement effects. Groups reuse current candidate totals; modular materializations survive subsequent statements. Canonical publication nodes track final multiplicity and are removed on cancellation. Native regression tests reject replay-sized map work and stale staged bag counts. This is removal of prior work, not proof of originality.

The initial preparation still uses the previous evaluator. Joins scan current inputs; maintained absence scans current inputs and previous output for affected keys. Catalog loops and overlay visibility scans remain. No persistence, concurrent access, full SQL or agent mode is added. The old installed baseline cannot execute the new absence grammar, so it is not presented as a matched absence benchmark.

The initial SQLite-only draft screen is not acceptance evidence: its oracle treated an unmatched UPDATE as an error and its rollback mutant was rejected by the constraint before demonstrating wrongly committed state. The corrected tests require zero-row UPDATE success and a valid rollback mutant that reaches the final-state mismatch. Frozen older `research/sql-maintenance` v2 evidence is unchanged.
