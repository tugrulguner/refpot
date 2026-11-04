# Maintained SQL: matched incremental control

## Qualified comparison path

`matched.py` executes indexed SQLite tables with real insert/delete/update triggers maintaining group sums and counts, against the installed native maintained-SQL implementation in both modes. SQLite join/filter/projection outputs are ordinary views; RefPot maintains them. A small SQLite wrapper checks the final-state assertion before commit and immediately rolls back an ordinary statement error. This is a competent incremental functional control, not a full-recomputation baseline or a speed comparison.

```sh
python3 research/sql-maintenance/matched.py \
  --candidate-python /absolute/path/to/candidate-venv/bin/python \
  --output /absolute/path/to/fresh-evidence-directory
```

The candidate interpreter must contain the real built wheel, not an editable/source substitute. The output records the imported package/extension paths and extension SHA-256. Final qualification must rebuild and rerun after native changes.

`workload-v2.json` contains all fixture rows and operations. Its two fixtures cover capacity/reservations and recorded-price/budget totals: the aggregate is SUM of stored amounts, not multiplication by a unit rate. A dimension's rate is returned by the join, not multiplied into the sum. This intentionally stays within the agreed SQL fragment; no foreign keys, arithmetic projections, or weighted aggregates are implied.

The matrix includes sparse and denser changes, both join inputs, dimension deletion/reinsertion, grouping-key moves, duplicate projection bags, last-group deletion, read-your-writes, planned rollback, temporary constraint violation and repair, rejected final commit, and an ordinary duplicate-primary-key error after a valid prefix.

An independent Python interpreter replays source operations before deriving expected rows. It does not trust source rows returned by either database. Every successful statement, failed statement and final transaction state is checked across both source tables and every declared relation. Persisted JSON is reread and compared to independently reconstructed histories, then all three engines' records are compared exactly. No representation-normalization exception hides empty groups or bag duplicates.

Regression tests in `tests/test_sql_maintenance_control.py` execute both engines and deliberately run a rollback-as-commit mutant and a dropped-write mutant against real SQLite. The oracle must reject both. It also rejects missing and altered persisted history.

## Retained, rejected first attempt

`control.py`, `candidate_adapter.py`, `workload.json`, and `evidence/sqlite-control.json` preserve the first delegated attempt; they are NOT qualification evidence. Parent review reproduced a concrete defect: the control committed before handling a requested rollback. Its oracle recomputed derived rows from the database's own source rows, so it accepted the wrong committed history. The candidate adapter also requested unsupported REFERENCES and arithmetic expressions, normalized away empty-group differences, and did not compare full per-transaction records against SQLite.

Do not use those old entry points or their timing/count output to support claims. The corrected comparison is versioned separately rather than silently rewriting that frozen attempt. No performance, durability, concurrency, novelty, or general SQLite-superiority claim follows from functional equality.
