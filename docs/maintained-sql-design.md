# Maintained SQL slice: implementation contract

Base: 9bef95543bd4d2292e93c0572cbfd0f809b5b7ce. This is an additive volatile preview, not all of M3, a release, durability, concurrency, or a novelty claim. Preserve native/core.cpp, the fixed-schema API/storage, and frozen historical research sources/evidence.

## Public path

Keep `from refpot.sql import Database`; all declarations and reads use `execute`:

- `CREATE MATERIALIZED VIEW name AS SELECT ...` declares an eagerly maintained bag relation. The first slice supports named projection/aliases, literal or column comparisons joined by AND, one equijoin, and grouped SUM/COUNT over one grouping key. Reject unsupported view constructs explicitly (including ORDER/LIMIT, global aggregates if nullable state cannot be represented, multiple SUM inputs). Unique addressable output column names required; aggregate outputs require aliases. Ordinary existing SQL remains compatible.
- `CREATE ASSERTION name CHECK (NOT EXISTS (SELECT * FROM relation))` requires a named table/view to be empty at commit. This deliberately narrow assertion grammar is explicit, not a general SQL standard compatibility claim. Users declare a violation view using ordinary expressions, not a hardcoded reservation operation.
- Named views participate in SELECT/joins/aggregates as bags, including duplicate rows. They are read-only; INSERT/UPDATE/DELETE must reject view targets even if a predicate would match no rows.
- DDL is outside transactions only. Declaring on populated tables builds only newly needed derived state, preserves existing rows, validates existing data, and publishes atomically. Rejected declarations leave no catalog fragments. Names and graph depth/width/work/row budgets are bounded.

## Transactions

Maintain derived results after each accepted mutation so read-your-writes includes changed views. Explicit transactions may temporarily violate declared assertions; validate against the complete final candidate at COMMIT, enabling multi-statement repair/reordering. Autocommit validates each statement. Ordinary syntax/binding/overflow/resource failures still abort the entire explicit transaction, matching current SQL behavior. Explain does not mutate or abort. A rejected COMMIT discards source and derived changes together. Retain native foundation callers' existing immediate-constraint defaults; new deferred operation must be explicit.

Publish with all fallible allocations/preparation complete. No partial graph changes on allocation failure or budget/overflow rejection. Construction, propagation and final validation are separate costs, measured honestly; no hidden full-catalog rebuild on CREATE. Generic cumulative-delta reevaluation currently exists: do not present it as per-statement optimal or hide its counters.

## Qualification

TDD vertical slices, real native tests first; installed wheel and sdist consumption later. Verify reservation/capacity and pricing models against independent full-state oracles after changes, rollback and commit; include inserts, updates/deletes on both join sides, duplicate projections, empty groups, overflowing intermediate/final sums, declaration on populated data, rejected writes to views, temporarily invalid then repaired explicit transactions, failed declarations and allocation cuts.

Compare complete workflows with competent incremental SQLite control (triggers/indexes and commit-time checks under the same declared semantics), not only full recomputation. Retain sparse and dense workloads, construction/maintenance/validation costs and losing cases. Feature availability, measured removed work, competitive advantage and originality are separate verdicts.

Deliver code, runnable installed examples, tests, canonical/generated documentation and a reviewed implementation PR. No merge/release authority carries over from PR37.
