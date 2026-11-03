---
title: Unreleased SQL preview
description: Canonical RefPot guidance and evidence with explicit scope.
---

> **Preview, not a published-package capability.** `from refpot.sql import Database, Result, SQLError` describes a new public API under development. It is **not included in the currently published package** and has not been verified in a published wheel. This documentation does not mark roadmap M1 complete. The existing fixed-schema `from refpot import Database, Row` API and its file/storage contract remain unchanged; the SQL preview uses separate in-memory state and has no persistence.

This is a RefPot-owned native execution path, not a SQLite wrapper. It is an intentionally small SQL subset. Unsupported syntax fails; it is not delegated to another database. There is no natural-language mode or ORM.

## Try the source example

The full example is [`examples/sql_preview.py`](../examples/sql_preview.py). It uses the public Python API directly and demonstrates table creation, positional parameters, a join with grouped aggregates, an explain result, read-your-writes, transaction rollback and commit, and volatile close. In a source checkout where the preview extension has been built and is importable, run:

```sh
python examples/sql_preview.py
```

The example does not take a native-library path, alter `sys.path`, or use `ctypes`. Because the SQL API is unreleased, this command is not an installation instruction for the currently published package and is not evidence of wheel availability.

## Python interface

```python
from refpot.sql import Database, Result, SQLError

with Database() as db:
    db.execute("CREATE TABLE inventory (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
    db.execute("INSERT INTO inventory VALUES (?, ?)", (1, 12))

    result = db.execute(
        "SELECT id, units FROM inventory WHERE units >= ? ORDER BY units DESC LIMIT ?",
        (5, 10),
    )
    assert isinstance(result, Result)
    assert result.columns == ("id", "units")
    assert result.rows == ((1, 12),)

    explanation = db.execute(
        "SELECT units FROM inventory WHERE id = ?", (1,), explain=True
    )
    print(explanation.plan)
```

- `Database()` creates a fresh volatile database. `Database(mode="overlay")` is the default; `mode="modular"` selects an alternate internal mode. Other mode values raise `ValueError`. These are preview implementation modes, not persistence, isolation, or performance guarantees.
- `execute(query, parameters=(), *, explain=False)` accepts a SQL string and positional parameters. Parameters are bound values, not SQL interpolation. `explain=True` returns a textual plan without scanning rows or changing database state. It still parses and binds the statement; explain errors do not abort an active transaction.
- Each call returns an immutable `Result`: `columns` is a tuple of output names, `rows` is a detached tuple of row-tuples, `affected` is the number of affected rows for DML (zero for queries/DDL), and `plan` is the textual operation plan. Each result value is a signed 64-bit integer or `None` for the empty global `SUM` result. Detached results remain usable after later writes or database close.
- `transaction()` is a context manager. Normal exit commits; an exception or a rejected executed statement aborts and rolls back the whole explicit transaction. A caught statement error does not make the transaction usable again: exit raises `SQLError`. Nested transactions and SQL transaction-control statements inside the context are rejected. DDL is not allowed inside a transaction. Outside an explicit context, successful mutations apply as individual operations.
- `stats()` returns cumulative native diagnostics. `statement_mutations` counts successfully staged mutation effects, including statements in subsequently rolled-back transactions. `source_mutation_applications` counts actual source-stage attempts, including rejected attempts; `full_bag_copied_entries` counts entries in completed full-bag materializations, not partial failed copies. `predicate_bindings` counts bound comparison operators; `predicate_tests` counts executed comparisons. The structural fields `prior_mutation_replays`, `catalog_copied_rows`, and `candidate_copied_entries` remain zero in this implementation. Those zero fields alone are not measurement evidence. None of these fields measures total allocations, total copy cost, peak memory, or speed; this preview dictionary is not a stable monitoring schema.
- `close()` is idempotent and discards all data. `with Database() as db:` closes on exit. There is no file to reopen and no durability or close-time persistence guarantee.
- A handle belongs to the process and thread that created it. Use or close from another process/thread raises `RuntimeError`; concurrent access is unsupported.
- Invalid SQL, binding errors and rejected executed statements raise `SQLError`. API argument type/range errors may raise `TypeError`, `ValueError` or `OverflowError`; use these names for the preview, not as a compatibility promise for the old API.

The older `from refpot import Database, Row` contract is separate: it takes a file path, stores the fixed-schema CRUD records and has its documented transaction/error behavior. This preview neither changes nor implements SQL through that class. See the [existing package contract](/package-contract/).

## Supported SQL subset

The schema and stored values are integer-only. Every table has one signed-64-bit integer primary-key column, followed by zero or more signed-64-bit `INTEGER NOT NULL` columns. The key is immutable. SQL identifiers are unquoted ASCII names, case-insensitive, at most 64 bytes, beginning with a letter. Schema changes (`CREATE TABLE`) are permitted only outside a transaction.

- **DDL:** `CREATE TABLE name (id INTEGER PRIMARY KEY, column INTEGER NOT NULL, ...)`.
- **Writes:** one-row `INSERT INTO table VALUES (...)`; `UPDATE table SET column = value [, ...] [WHERE ...]`; and `DELETE FROM table [WHERE ...]`. Update/delete predicates can compare a column to an integer literal or `?` binding. An unmatched predicate affects zero rows. A multirow update/delete statement is applied atomically.
- **Reads:** `SELECT` named columns or `*` from one table, optionally with one `JOIN`/`INNER JOIN` whose equality predicate relates the two input tables. Optional `WHERE` comparisons are joined by `AND`; supported operators are `=`, `!=`, `<>`, `<`, `<=`, `>` and `>=`.
- **Aggregates:** `COUNT(*)`, `SUM(column)`, and zero or one `GROUP BY` column. With grouping/aggregation, nonaggregate projected columns must be the grouping column. Empty global `COUNT(*)` returns zero; empty global `SUM(...)` returns `None` (SQL NULL). Sums are accumulated wide and raise on a final value outside signed-64-bit range. SQLite integer `SUM` raises on intermediate integer overflow rather than converting to float; RefPot can therefore return a valid final sum when intermediate values overflow signed 64-bit and later cancel.
- **Ordering and bounds:** `ORDER BY` selected output columns/aliases or explicitly qualified selected columns, with `ASC`/`DESC` and multiple terms. `LIMIT` accepts an integer literal or parameter from 0 through 100000. No stable order is promised for rows tied on all requested order terms.
- **Transactions:** `BEGIN`, `COMMIT` and `ROLLBACK` are available at the SQL engine level, while Python callers should use `transaction()` for scoped transactions. Do not mix transaction-control statements with the Python context manager.

Parameters must be exact Python integers in signed-64-bit range. `bool`, floats, strings and `None` are rejected; there are no named parameters or stored NULL/text columns. A `None` result is produced only for empty global `SUM` in the current subset. Unknown or ambiguous columns are rejected even when input relations are empty. Missing or extra positional bindings are errors, and duplicate projected rows are retained.

## Limits and unsupported features

The preview enforces bounded work, not an overall process-memory or wall-clock deadline. Current guards include 64 KiB SQL text, 8192 tokens/parameters, 128 tables, 64 columns per table, 100000 total stored rows, 10000 accumulated transaction mutation effects, 100000 output rows/groups, and one million logical visits per SELECT or mutation scan. `LIMIT` bounds returned rows, not scan work or sorting work.

Unsupported features include text or nullable stored columns, expressions/arithmetic, `OR`, outer joins, multiple joins or grouping columns, subqueries, CTEs, `DISTINCT`, `HAVING`, `UNION`, SQL comments, quoted identifiers, named parameters, multi-row `VALUES`, `DROP`/`ALTER`, secondary indexes, cursors, asynchronous execution/cancellation, persistence, concurrent use and natural-language `agent=True`. There is no SQLite SQL, file-format or C API compatibility promise.

## Failure boundary and remaining costs

A rejected executed statement aborts the entire explicit transaction, unlike the fixed-schema API's behavior where catching a validation/missing/duplicate error does not discard earlier valid staged operations. A Python transaction context records a failed statement and raises on exit even if the caller caught the original error. `explain=True` does not execute or abort a transaction. If converting a native result to Python fails after execution, the preview closes the handle rather than claiming the already-executed mutation rolled back. This is fail-closed volatile ownership, not an outcome-recovery protocol.

The SQL preview is not the complete relational architecture in the roadmap. It has no durable storage, snapshot/recovery protocol, concurrent readers, multiwriter semantics, free-threading qualification, or natural-language interface. The supported subset is not broad SQL support. SQL predicates and maintained filters use the same bound comparison primitive; SQL and maintained groups share checked-count/wide-sum aggregation. Both overlay and modular modes use these helpers, so reuse is not an overlay-only advantage or proof of a universal intermediate representation. Source-only SQL transactions extend their private candidate in place, discard the whole candidate on failure, and retain a mutation count rather than replayable requests. CREATE appends an empty relation without copying existing rows; row admission uses transaction-aware counts. Modular mode still materializes each touched base relation once per transaction; overlay mode retains signed changes and preallocated publication nodes. General maintained-definition append still reevaluates cumulative derived changes, and ad hoc SQL has no maintained query cache. Joins use nested loops; ordering materializes and sorts before applying `LIMIT`. Diagnostic counters and local comparisons do not by themselves establish an architectural or performance advantage. No claim here closes roadmap M1 or the separate storage, concurrency, durability, installed-artifact and broader qualification work.

[Download this page as Markdown](/docs/reference-sql-preview.md)
