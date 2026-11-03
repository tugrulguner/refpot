# Local native SQL slice contract

This slice advances ordinary querying over the shared-change foundation. It is a volatile,
in-process research preview with a Python entry point, not an installed package feature or a
completed M1 milestone. Existing `refpot.Database` / `Row` behavior and storage remain unchanged.
No package installation, provider access or publication is part of this experiment.

## Ownership and API

`Database(library=path, mode="overlay")` loads an explicitly built native shared library;
`mode="modular"` retains the competent storage comparator. `execute(query, parameters=(),
explain=False)` returns detached immutable columns/rows, affected count and an inspectable plan.
SQL parsing, binding, scanning, joining, aggregation and mutation must execute in C++; Python
validates arguments and decodes results only. SQLite is permitted exclusively in tests.

Each handle is owned by its creating process/thread. Closing discards all volatile state.
No persistence, concurrent access or snapshot-isolation claim is made. Native scans borrow
rows for callback lifetime and must not permit reentrant mutation from a callback.

## Declared narrow SQL target

- CREATE TABLE with an immutable first-column INTEGER PRIMARY KEY and INTEGER NOT NULL columns.
- Parameterized INSERT VALUES, UPDATE SET and DELETE FROM, with explicit column binding.
- SELECT projection and *, comparisons combined with AND, a bounded inner equijoin,
  COUNT(*) and SUM(column), one grouping key, ORDER BY and LIMIT.
- Signed-64-bit values; no coercion of Python bool, float, text or None. Empty global COUNT is
  zero and empty SUM is NULL. Duplicated projected tuples are preserved.
- Unknown/ambiguous columns must fail even on empty input. Unsupported syntax, multiple
  statements, nullable table columns and mismatched parameter counts fail explicitly.
- Ad hoc SELECT must not register permanent definitions or require maintained domain models.
- Explain binds without executing the statement or changing transaction state.

Implemented grammar restrictions and any uncompleted target must be listed in README after
execution; this specification is not evidence that every target already works.

## Transactions

Autocommit publishes each successful mutation. BEGIN/COMMIT/ROLLBACK provide read-your-writes.
Any rejected statement aborts the whole explicit transaction, unlike the installed fixed-schema
package's statement-error contract. A Python transaction context must prevent later statements
from silently becoming autocommits after a caught error. No nested transactions or DDL inside
an explicit transaction. Closing an uncommitted handle discards changes.

Accepted statements may reprepare the accumulated mutation list; COMMIT publishes its already
prepared candidate. The costs of replaying that list and catalog rebuild during CREATE must
remain explicit. Neither is a final transaction/canonical-catalog design decision.

## Qualification

Use independent SQLite results for the supported intersection, including empty results,
duplicates, ties, signed limits, join fan-out and grouped arithmetic. Separately verify intentionally
different strict typing and whole-transaction abort behavior. Require native tests and sanitizers,
Python ownership/lifetime checks, deterministic rejection tests and repeated runnable examples
from an outside-checkout consumer directory. Keep exact source and binary hashes with test logs.
No installed-wheel qualification is possible under the current no-install restriction.
