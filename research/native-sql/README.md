# In-process native SQL preview

This is a working **local, volatile SQL/Python slice** over RefPot's native shared-change
foundation. It does not use SQLite for execution and does not require a maintained domain model,
a subprocess database service or an agent. SQLite appears only in independent tests.

It is not the installed `refpot.Database` API, a released wheel or completion of roadmap M1.
The old package and storage format are unchanged. Nothing is installed by these commands.

## Build and run

From the repository root, with Python 3 and an existing C++17 compiler:

```sh
python3 research/native-sql/run.py --output "$HOME/.cache/refpot-native-sql/run-1"
```

The output directory must be new. The runner compiles a shared library, executes native normal
and ASan/UBSan tests, runs Python/SQLite differential tests, and copies the adapter, library and
example into an outside-checkout consumer directory. It runs that example twice in each mode.
The saved manifest includes exact source/library hashes, actual commands, logs and environment.
Leak detection is disabled. Python loads the normal library; sanitizer coverage applies to the
native scan, SQL, parser and C bridge test executables.

On macOS, run the already-built example directly:

```sh
python3 examples/experimental_native_sql.py --library "$HOME/.cache/refpot-native-sql/run-1/librefpot_sql.dylib"
```

On Linux, the runner names the library `librefpot_sql.so`; Linux execution is not qualified by
macOS results. Windows is unsupported. `--mode modular` runs the alternative storage mode.

## Python usage

In the generated consumer directory, `native_sql.py` is next to your script:

```python
from native_sql import Database

with Database(library="./librefpot_sql.dylib") as db:
    db.execute("CREATE TABLE stock (id INTEGER PRIMARY KEY, units INTEGER NOT NULL)")
    db.execute("INSERT INTO stock VALUES (?, ?)", (1, 10))
    with db.transaction():
        db.execute("UPDATE stock SET units = ? WHERE id = ?", (6, 1))
        result = db.execute(query="SELECT units FROM stock WHERE id = ?", parameters=(1,))
        assert result.rows == ((6,),)
    print(result.columns, result.rows)
```

The example also creates two ordinary tables and executes a parameterized joined, grouped,
ordered query. It demonstrates a price change visible inside a transaction, rollback restoring
the previous totals, then explicit commit. No durable query definition is registered.

## Implemented subset

- CREATE TABLE: first column `INTEGER PRIMARY KEY`, subsequent columns `INTEGER NOT NULL`.
  Identifiers are unquoted ASCII, case-insensitive, at most 64 bytes and begin with a letter.
  Duplicate columns/tables fail. Keys cannot be updated.
- INSERT INTO table VALUES: one complete row, signed integer literals or positional `?` bindings.
- UPDATE SET: column/value assignments; DELETE FROM; optional WHERE comparisons combined with AND.
  No match affects zero rows. Multiple matching rows form one atomic statement.
- SELECT: named projections or `*`; optional `AS` aliases; one JOIN/INNER JOIN with an equality
  relating the two inputs; WHERE column compared to integer/parameter using `= != <> < <= > >=`.
- COUNT(*), SUM(column), zero or one GROUP BY column. Nonaggregate projections must be that group
  column. Empty global COUNT is zero; empty global SUM is NULL. SUM uses a wide accumulator and
  rejects final values outside signed-64-bit range rather than returning SQLite's float promotion.
- ORDER BY selected output names/aliases or explicitly qualified selected columns, with ASC/DESC;
  multiple ordering terms; LIMIT integer/parameter from zero to 100000. Ties without sufficient
  ordering terms are not a portable stable-order promise.
- BEGIN/COMMIT/ROLLBACK and Python `transaction()`, with read-your-writes; `explain=True` binds
  and returns a textual physical-operation plan without scanning or publishing.

Unknown and ambiguous columns fail even on empty relations. Missing/extra bindings fail.
Projected duplicates remain duplicate result rows. Parameters reject bool, floats, strings and
None rather than coercing them. Returned results are immutable detached tuples and remain valid
after mutation or close. Ownership is restricted to the creating process/thread.

Not supported: text/nullable stored columns, expressions/arithmetic in SQL, OR, outer joins,
multiple joins/group keys, subqueries, CTEs, DISTINCT, HAVING, UNION, SQL comments, quoted names,
named parameters, multi-row VALUES, DROP/ALTER, secondary indexes, cursors, asynchronous
cancellation, persistence, concurrent use, or natural-language `agent=True`. Unsupported syntax
is rejected; there is no fallback backend. SQL parsing is native; no language-intent rules exist.

## Transaction and failure contract

A rejected executed statement aborts the whole explicit transaction. This deliberately differs
from the installed fixed-schema package's statement-error behavior. A caught error inside a
Python transaction context prevents subsequent accidental autocommits and causes context exit
to fail. Inner transaction-control SQL/nested contexts are rejected. Explain failures do not
abort the transaction. DDL is unsupported inside a transaction.

Native candidates and their publication resources are prepared before publication. At the C/Python
response boundary, allocation/encoding failure can happen after execution; the bridge marks
such handles unusable and Python closes the volatile database rather than pretending the write
was rolled back. A NULL/invalid bridge response also closes the handle. This is fail-closed local
ownership, not a durable outcome-recovery protocol. Python-level allocation qualification remains
limited; no claim of complete allocator-failure coverage is made.

Close discards all data. Use a context manager or explicit `close()`; there is no destructor-based
resource guarantee. There is no file to reopen.

## Costs and limits

The query scan reads the same committed/candidate visibility as relational maintenance, without
exporting every table first. Query operators are currently separate ad hoc execution code;
this does not prove a universal expression representation or eliminated duplicate evaluation.

Explicit transactions reprepare their accumulated mutation list after each statement. Python
managed transactions bind once for control-ownership inspection and again for execution.
CREATE rebuilds the source-only catalog and copies existing rows atomically, guarded by the
global catalog-row budget. INSERT counts visible rows across the catalog before admission. Joins are nested loops; ORDER BY materializes then sorts, and
LIMIT is applied afterwards. These costs are explicit prototype limitations, not hidden wins.

Limits include SQL 64 KiB, 8192 tokens/parameters, 128 tables, 64 columns/table, 100000 total stored rows,
10000 accumulated mutation effects, 100000 returned rows/groups and one million logical scan
visits per SELECT or mutation scan. These are deterministic operation guards, not a process
memory ceiling, elapsed-time deadline or full allocation accounting.

## Qualification

`tests/test_native_sql.py` discovers the complete runner in repository unittest discovery.
The local campaign passed 1680 ordered query comparisons against SQLite across both storage
modes, plus full-state/read-your-writes checks after 240 update transactions. Native tests cover
594 truncated parser prefixes and 4000 seeded malformed strings, signed limits, fan-out,
empty aggregates and transaction rejection under normal and ASan/UBSan builds. These counts
repeat the same cases in sanitizer builds, not additional independent cases.

The C bridge's successive allocation-failure sweep observed 20 pre-result failures and 3 fatal
post-execution response failures for the tested INSERT. It does not cover every allocation
site in every query or Python decoding. An injected Python Result-construction MemoryError after
a real native INSERT also verifies fail-closed ownership. A parent regression caught catalog creation deleting
existing rows; another caught incomplete success JSON when stream allocation failed. Both
have executable regression tests. Independent review found no semantic blocker but identified
catalog-rebuild admission guarded only by per-table limits. A global 100000-row cap and explicit rebuild
guard now bound that path; a small injectable native budget verifies cross-table admission,
transactional replacement and rejection rollback. The earlier delegated smoke pass did not qualify this code.

The outside-checkout consumer uses copied files and a real native library, not a mock or an
editable import. It is not installed-wheel qualification. No package install, commit, push,
PR, release, model call or publication was performed by this slice.
