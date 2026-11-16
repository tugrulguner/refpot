# Unreleased SQL preview (`refpot.sql`): optional bounded persistence

> **Preview, not a published-package capability.** `from refpot.sql import Database, Result, SQLError` describes a source-preview API under development. It is **not included in the currently published 0.1.2 package** and has not been verified in a published wheel. This does not mark roadmap M1, M3, or M4 complete. The existing fixed-schema `from refpot import Database, Row` API and its file/storage contract remain unchanged. SQL preview defaults to volatile state, with optional bounded persistence when a path is supplied.

This is a RefPot-owned native execution path, not a SQLite wrapper. It is an intentionally small SQL subset. Unsupported syntax fails; it is not delegated to another database. The bounded natural-language mode described below is an unreleased source preview; ORM is not provided.

## Try the source example

The core example is [`examples/sql_preview.py`](../examples/sql_preview.py). The persistent whole-model example is [`examples/sql_persistence.py`](../examples/sql_persistence.py); it verifies recovered derived state and that capacity and missing-resource assertions remain enforced after reopen. The bounded source-only read-agent example is [`examples/sql_agent.py`](../examples/sql_agent.py); its fixture mode is provider-free by default. See the separate [agent-query evaluation and remaining M2 gates](agent-query-evaluation.md). In a source checkout where the preview extension has been built and is importable, run:

```sh
python examples/sql_preview.py
python examples/sql_persistence.py
python examples/sql_evolution.py
python examples/sql_agent.py
```

The example does not take a native-library path, alter `sys.path`, or use `ctypes`. Because the SQL API is unreleased, this command is not an installation instruction for the currently published package and is not evidence of wheel availability.

## Read-only natural-language queries

Natural-language query generation is an explicitly selected, bounded source-preview feature; it is not in published 0.1.2 or its wheels. `Database(agent=config)` supplies configuration, while `execute(query="...", agent=True)` selects generation for that call. Ordinary SQL remains provider-free. The feature is experimental, read-only, and does not establish M2 completion or semantic correctness. The following remote example requires `OPENROUTER_API_KEY` to be configured securely in the process environment and sends the question plus authorized schema metadata to OpenRouter:

```python
from refpot.agent import AgentConfig
from refpot.providers import OpenRouter
from refpot.sql import Database

config = AgentConfig(
    generator=OpenRouter(model="nvidia/nemotron-3.5-super-vl:free"),
    relations=("items",),
    disclose_schema=True,
)
with Database(agent=config) as db:
    db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, quantity INTEGER NOT NULL)")
    db.execute("INSERT INTO items VALUES (?, ?)", (1, 8))
    result = db.execute(query="Show item quantities above five", agent=True)
    assert result.generation is not None
    print(result.rows)
    print(result.generation.query, result.generation.parameters)
```

`disclose_schema=True` is an explicit opt-in to send the question, authorized relation names, ordered output-column names, and whether each relation is derived to the configured generator. It does not disclose rows, view definitions/private inputs, or database revision. `relations` is an immutable tuple of one to 128 exact catalog names, each at most 64 UTF-8 bytes. An authorized view is a read capability; its underlying inputs are not automatically authorized for direct queries. The configured generator is trusted caller Python: it can block, hang, or perform its own effects; RefPot cannot sandbox or preempt arbitrary callables and promises no hard deadline. Generation is not entered within an active transaction, and refusal preserves that transaction; use explicitly inspected or user-written ordinary SQL when read-your-writes is needed. The native read-only binder checks authorized tables/joins/subqueries and schema freshness regardless of generator output. It rejects mutations and unsupported authority, but binder acceptance is not proof that the SQL reflects user intent.

`explain=True` can inspect the generated query without scanning or mutating. Successful agent results carry immutable generation metadata (`query`, `parameters`, `assumptions`); ordinary SQL results carry `generation=None`. Clarification and decline have distinct typed errors. Provider failures become sanitized `AgentError`; SQL syntax and authority failures remain SQL errors. The fixture-first [`examples/sql_agent.py`](../examples/sql_agent.py) runs without network by default; `--live` is an explicit OpenRouter opt-in. The bounded frontend comparison and unresolved quality gates are in [agent-query evaluation](agent-query-evaluation.md).

`OpenRouter(model=..., api_key_env="OPENROUTER_API_KEY", timeout=30, max_tokens=2048)` is a standard-library-only adapter. It accepts a fixed `:free` model, verifies zero prompt/completion prices in the public model catalog, sends zero-price routing ceilings with fallbacks disabled, and requires the response to report the configured model and zero cost before executing its proposal. Catalog/response bodies are capped at 4 MiB/1 MiB; generated JSON content and query strings at 64 KiB. `timeout` is a finite positive socket timeout of at most 120 seconds, not a total wall-clock deadline. `max_tokens` is an integer from one through 2048. There are no automatic retries, SQL repairs, tool calls, or paid fallbacks. Availability and provider-reported billing depend on OpenRouter; fail-closed checks are not an independent billing guarantee. The adapter reads only the named environment variable, not application files or Hermes settings.

Other trusted generators can consume the immutable `GenerationRequest` and return `QueryProposal(query, parameters, assumptions)`, `Clarification(questions)`, or `Decline(reason)` from `refpot.agent`. `ClarificationRequired.questions` and `QueryDeclined.reason` expose the corresponding refusal details. Material unstated business rules require clarification, not silent assumptions. Passing `parameters` with natural-language input is unsupported; generated bindings must be exact signed-64-bit integers. Calling `agent=True, explain=True` still invokes generation, so reuse the returned SQL explicitly when no further model call is wanted.

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

- `Database(path=None, *, mode="overlay", agent=None)` selects storage, execution mode, and optional agent configuration. `None` creates a volatile database. A `str` or `PathLike[str]` path opens the separate persistent SQL format; the parent directory must already exist. `mode="modular"` selects the alternate internal execution mode. Other mode values raise `ValueError`. These are preview modes, not isolation or performance guarantees.
- `execute(query, parameters=(), *, explain=False, agent=False)` accepts a SQL string and positional parameters by default; `agent=True` selects natural-language generation using the separately configured generator. Parameters are bound values, not SQL interpolation. `explain=True` returns a textual plan without scanning rows or changing database state. It still parses and binds the statement; explain errors do not abort an active transaction.
- Each call returns an immutable `Result`: `columns` is a tuple of output names, `rows` is a detached tuple of row-tuples, `affected` is the number of affected rows for DML (zero for queries/DDL), and `plan` is the textual operation plan. Each result value is a signed 64-bit integer or `None` for the empty global `SUM` result. Detached results remain usable after later writes or database close.
- `transaction()` is a context manager. Normal exit commits; an exception or a rejected executed statement aborts and rolls back the whole explicit transaction. A caught statement error does not make the transaction usable again: exit raises `SQLError`. Nested transactions and SQL transaction-control statements inside the context are rejected. DDL is not allowed inside a transaction. Outside an explicit context, successful mutations apply as individual operations.
- `stats()` returns cumulative native diagnostics. `statement_mutations` counts successfully staged mutation effects, including statements in subsequently rolled-back transactions. `source_mutation_applications` counts actual source-stage attempts, including rejected attempts; `full_bag_copied_entries` counts entries in completed full-bag materializations, not partial failed copies. `predicate_bindings` counts bound comparison operators; `predicate_tests` counts executed comparisons. The structural fields `prior_mutation_replays`, `catalog_copied_rows`, and `candidate_copied_entries` remain zero in this implementation. Those zero fields alone are not measurement evidence. None of these fields measures total allocations, total copy cost, peak memory, or speed; this preview dictionary is not a stable monitoring schema.
- `checkpoint()` explicitly writes a bounded committed-state snapshot. It is rejected inside an active transaction without aborting that transaction. Ordinary commits do not write a full snapshot. `close()` is idempotent, does not checkpoint, and discards only volatile state; persistent acknowledged state is reopened from disk.
- A handle belongs to the process and thread that created it. Persistent files also have exclusive single-opener ownership. Use or close from another process/thread raises `RuntimeError`; concurrent access is unsupported.
- Invalid SQL, binding errors and rejected executed statements raise `SQLError`. API argument type/range errors may raise `TypeError`, `ValueError` or `OverflowError`; use these names for the preview, not as a compatibility promise for the old API.

The older `from refpot import Database, Row` contract is separate: it takes a file path, stores the fixed-schema CRUD records and has its documented transaction/error behavior. This preview neither changes nor implements SQL through that class. See the [existing package contract](package-contract.md).

## Optional whole-model persistence

Persistent mode is a bounded source-preview feature. It persists schema/catalog metadata, logical definitions, named assertions, and weighted bags for both source and engine-internal derived relations. Recovery reconstructs and validates the complete model before the handle is exposed; it does not replay SQL, Python callbacks, or historical mutation requests. The canonical net changes across all changed bags are stored in one durable record/frontier. The record is synchronized before prepared in-memory changes are published. Ordinary commits do not scan, serialize, or write a full-model snapshot; remaining costs include transaction-local maintenance/visibility scans and retained derived state.

`checkpoint()` is explicit and snapshots committed state only. The encoded snapshot is bounded to 64 MiB and the WAL to 128 MiB; capacity is checked before acknowledging an operation, and WAL pressure requires a checkpoint. There is no automatic checkpoint on close. Persistent storage uses a separate versioned format and `.wal`, `.tmp`, and `.lock` sidecars; it does not migrate or reinterpret the fixed-schema format. The bounded view-replacement operation below is the only definition-evolution operation; backup/restore and general schema evolution are not provided.

The persistent handle is exclusive to one process/thread and one opener. After uncertain storage I/O the writer is poisoned; close and reopen, inspect state, and do not blindly retry the operation. The implementation relies on filesystem sync and atomic-rename behavior. Process/fault testing is not proof of physical power-loss safety, production durability, or broad filesystem/platform qualification.

## Supported SQL subset

The schema and stored values are integer-only. Every table has one signed-64-bit integer primary-key column, followed by zero or more signed-64-bit `INTEGER NOT NULL` columns. The key is immutable. SQL identifiers are unquoted ASCII names, case-insensitive, at most 64 bytes, beginning with a letter. Schema changes (`CREATE TABLE`) are permitted only outside a transaction.

- **DDL:** `CREATE TABLE name (id INTEGER PRIMARY KEY, column INTEGER NOT NULL, ...)`.
- **Writes:** one-row `INSERT INTO table VALUES (...)`; `UPDATE table SET column = value [, ...] [WHERE ...]`; and `DELETE FROM table [WHERE ...]`. Update/delete predicates can compare a column to an integer literal or `?` binding. An unmatched predicate affects zero rows. A multirow update/delete statement is applied atomically.
- **Reads:** `SELECT` named columns or `*` from one table, optionally with one `JOIN`/`INNER JOIN` whose equality predicate relates the two input tables. Optional `WHERE` comparisons are joined by `AND`; supported operators are `=`, `!=`, `<>`, `<`, `<=`, `>` and `>=`.
- **Aggregates:** `COUNT(*)`, `SUM(column)`, and zero or one `GROUP BY` column. With grouping/aggregation, nonaggregate projected columns must be the grouping column. Empty global `COUNT(*)` returns zero; empty global `SUM(...)` returns `None` (SQL NULL). Sums are accumulated wide and raise on a final value outside signed-64-bit range. SQLite integer `SUM` raises on intermediate integer overflow rather than converting to float; RefPot can therefore return a valid final sum when intermediate values overflow signed 64-bit and later cancel.
- **Ordering and bounds:** `ORDER BY` selected output columns/aliases or explicitly qualified selected columns, with `ASC`/`DESC` and multiple terms. `LIMIT` accepts an integer literal or parameter from 0 through 100000. No stable order is promised for rows tied on all requested order terms.
- **Transactions:** `BEGIN`, `COMMIT` and `ROLLBACK` are available at the SQL engine level, while Python callers should use `transaction()` for scoped transactions. Do not mix transaction-control statements with the Python context manager.

Parameters must be exact Python integers in signed-64-bit range. `bool`, floats, strings and `None` are rejected; there are no named parameters or stored NULL/text columns. A `None` result is produced only for empty global `SUM` in the current subset. Unknown or ambiguous columns are rejected even when input relations are empty. Missing or extra positional bindings are errors, and duplicate projected rows are retained.

## Maintained relations and assertions

The source-preview build also accepts a bounded, eagerly maintained relational declaration subset. A materialized view stores a bag result: duplicate rows and their multiplicities are preserved, and views can be read by ordinary `SELECT` and joins. Views are read-only; `INSERT`, `UPDATE` and `DELETE` reject them as targets.

```sql
CREATE MATERIALIZED VIEW paid_totals AS
SELECT account_id AS account, SUM(amount) AS total, COUNT(*) AS n
FROM payments
WHERE status = 1
GROUP BY account_id
```

A view query may project columns, apply comparisons joined with `AND` (each comparison is a column against one column or an integer literal), use at most one equijoin, and group by one key with `SUM` and/or `COUNT(*)`. Aggregate outputs need aliases; projected columns in an aggregate must be the grouping key; only one distinct `SUM` input is supported. Output names must be unique and addressable. `ORDER BY`, `LIMIT`, global aggregates and other unsupported query forms are rejected for maintained views. This restriction is specific to view declarations; ordinary SELECT keeps its documented ordering, limit, and global aggregate behavior.

Assertions use the deliberately narrow form `CREATE ASSERTION name CHECK (NOT EXISTS (SELECT * FROM relation))`. The named table or view must be empty when the assertion is created and at subsequent validation. Rejected creation leaves the name reusable. Relation names beginning with `refpot_internal_` are reserved for engine-generated definitions. Assertions are checked after each autocommit mutation and at explicit `COMMIT`; an explicit transaction may temporarily violate an assertion and repair it before commit. A failed commit discards the entire explicit transaction. DDL (tables, views and assertions) is forbidden inside explicit transactions. As elsewhere in this preview, an ordinary executed error aborts the whole explicit transaction. `explain=True` parses and binds but does not mutate or abort an active transaction.

Creating a maintained view over populated inputs computes the newly declared derived state only; it does not copy existing source rows into a replacement catalog. It does scan inputs to calculate that new state, and the declaration can be rejected by the work or intermediate-row limits.

### Exact reuse by ordinary queries

An eligible ordinary `SELECT` can reuse an existing maintained view whose bound
source identity, ordered projection, and ordered filter predicates match exactly.
Column/table aliases do not change that match. Output labels remain those requested
by the query; duplicate multiplicities, `ORDER BY`, and `LIMIT` retain their ordinary
semantics. `explain=True` reports `MAINTAINED_REUSE <view>` when selected.

This bounded optimization excludes joins, absence queries, aggregates/grouping,
active transactions, and restricted read-only agent execution. Those paths retain
the original evaluator, including transaction-local read-your-writes. A nonmatching
query falls back; no permanent view is created by a read. Existing views still incur
their normal construction and write-maintenance costs.

A lazy semantic index holds catalog metadata, not query results or row copies. Its
first eligible read after a successful catalog change rebuilds the index privately;
view replacement and reopen cannot reuse stale metadata. The diagnostic
`stats()["reuse_definition_visits"]` counts definition entries inspected while
building that index, including partial failed attempts; it is not a total-work,
memory, or speed metric. Index construction, retained metadata and per-query lookup
have costs, and small or nonmatching reads may be slower. No general speedup is
promised. Run `python examples/sql_query_reuse.py` in a built source checkout for
reuse and fallback examples. This remains unreleased SQL-preview behavior.

### Atomic maintained-definition replacement

Use `ALTER MATERIALIZED VIEW name AS SELECT ...` to replace one view, outside explicit transactions:

```sql
ALTER MATERIALIZED VIEW counted AS
SELECT resource, units FROM reservations WHERE status >= 1
```

This is an explicit offline migration on the exclusively owned handle, not a background refresh.
The target must already be a public maintained view. The new query uses the same maintained
SELECT subset and must have the same output column names and order. Source tables, internal
relations, missing targets, changed output shape, unknown columns and dependency cycles are
rejected. A new dependency may be a later-created independent view; self-reference and a
reference back through a dependent view are rejected. One call replaces one view, not a group
of definitions. Repeated replacement removes obsolete internal nodes rather than accumulating
old versions.

The native engine prepares the replacement and its transitive dependents privately, then
validates every existing named assertion against that candidate. It preserves source rows,
unrelated definitions/results, and assertion names/targets. The replacement can be rejected
because the newly computed state violates an assertion even though the old state is valid.
A rejected migration leaves the old definition and results in force; the caller can repair
source data explicitly and try again. Later ordinary mutations use the accepted definition.
The runnable [migration/reopen example](../examples/sql_evolution.py) demonstrates this with
provisional reservations that would exceed capacity under the new rule.

`explain=True` parses and binds the replacement without evaluating its data or publishing it;
it cannot promise that assertions, work limits or storage capacity will pass at execution.
The existing DDL/transaction rules still apply: executed DDL inside a transaction aborts it,
while explain errors do not. Results retain the ordinary DDL contract: no rows and zero
`affected`; detached earlier query results are not rewritten. There is no prepared-query or
natural-language interpretation cache to invalidate in this preview.

In persistent mode, catalog changes and accepted affected bags cross one synchronized migration
WAL frontier before in-memory publication. Reopening after an uncertain append yields the
complete old or new model, never a mixture; acknowledged replacement survives WAL recovery
and checkpoint recovery. Uncertain I/O poisons the handle, just as for ordinary writes.
All fallible preparation, validation and encoding precede that frontier. Existing row/work,
64 MiB encoded-state and 128 MiB WAL limits still apply; rejection for capacity precedes
acknowledgment. Recalculation and retained candidate bags consume work and memory, so this is
not an online migration, constant-time replacement or process-memory bound.

Earlier SQL-preview records remain readable by this implementation. The migration record is
new: older preview binaries cannot read its WAL record, and reopening an evolved model with
an older binary is unsupported even after checkpointing. This does not migrate the separate
published fixed-schema format. Table/column changes, assertion editing, multi-definition
migration transactions, online schema evolution and backup/restore remain future work.

### Missing-resource constraints

An inner join cannot expose references whose target row is missing. Declare a maintained
absence relation, then assert that it remains empty:

```sql
CREATE MATERIALIZED VIEW missing AS
SELECT r.id, r.resource FROM reservations AS r
WHERE NOT EXISTS (SELECT * FROM capacity AS c WHERE c.resource = r.resource)

CREATE ASSERTION resource_exists CHECK (NOT EXISTS (SELECT * FROM missing))
```

This is a bounded correlated `NOT EXISTS` form: one outer relation, one inner relation,
`SELECT *` or `SELECT 1` inside the subquery, and exactly one equality between qualified
outer and inner column references. Reversed equality is accepted; self-reference requires
distinct aliases. Both inputs may be maintained bags. Any positive matching right-side
multiplicity excludes the left row; duplicate left rows retain their multiplicity.
Deleting the last matching right row exposes the left rows again. Missing-resource
violations can be repaired before explicit commit, just like capacity violations.

The same projection-only form works in ordinary `SELECT`. It cannot be combined with
another predicate, join, aggregate, grouping, ordering, or limit in that statement.
Create a named absence view and query it separately for those supported operations.
Other subqueries remain unsupported. The runnable
[`examples/sql_maintenance.py`](../examples/sql_maintenance.py) demonstrates both capacity
and missing-resource assertions, including rejection and delete/reinsert repair.

### Transaction-local propagation

After the first statement prepares a private candidate, subsequent statements propagate
only their new signed effects through the declared graph. The candidate retains canonical
net effects for publication separately from the current statement's propagation effects.
Grouped sums/counts update affected keys from their previous candidate totals using wide
accumulation; joins include simultaneous changes to both inputs exactly once. Publication
nodes are refreshed only for changed tuples, including multiplicity changes and cancellation.
Modular mode retains each affected materialized bag rather than copying it again per statement.

This removes cumulative derived-change replay on append, not all population-dependent work.
The initial preparation still uses the existing evaluator. Joins still scan current candidate
inputs; maintained absence scans its inputs and prior output to replace affected keys. Overlay
visibility merges committed rows with accumulated effects. Catalog bookkeeping remains per
statement. Row-count metadata is retained per relation; statement deltas and prepared insertion
nodes also consume memory. Valid native publication remains allocation-free; parsing and
returning a SQL `COMMIT` result are outside that native publication claim.

## Limits and unsupported features

The preview enforces bounded work, not an overall process-memory or wall-clock deadline. SQL guards include 64 KiB text, 8192 tokens/parameters, up to 128 public relations and 128 assertions, 64 columns per relation, 100000 total source rows, 10000 accumulated transaction mutation effects, 100000 rows/groups for ordinary query results, and one million logical visits per SELECT or mutation scan. For maintained relations, each internal relation is capped at 100000 logical rows, a derived delta at 200000 distinct keys, maintenance work at 1000000 steps per stage/declaration, and the internal catalog at 1024 definitions across source and derived relations. A bounded intermediate can exceed its cap and be rejected even if a later filter or projection would make the final result small. These are current implementation caps, not throughput claims. `stats()["maintenance_steps"]` is a cumulative work counter, not a speed measure. `LIMIT` bounds returned rows, not scan work or sorting work.

Unsupported SQL features include text or nullable stored columns, expressions/arithmetic, `OR`, outer joins, multiple joins or grouping keys, subqueries other than the bounded correlated `NOT EXISTS` form above, CTEs, `DISTINCT`, `HAVING`, `UNION`, SQL comments, quoted identifiers, named parameters, multi-row `VALUES`, `DROP` and `ALTER` other than the bounded maintained-view replacement above, secondary indexes, cursors, asynchronous execution/cancellation, and concurrent use. The bounded read-only natural-language `agent=True` path is documented above; it is not broad SQL support or M2 completion. Persistence is available only through the bounded optional file-backed preview described above; general schema migrations, backup/restore, and a broad durability guarantee are not provided. There is no SQLite SQL, file-format or C API compatibility promise.

## Failure boundary and remaining costs

A rejected executed statement aborts the entire explicit transaction, unlike the fixed-schema API's behavior where catching a validation/missing/duplicate error does not discard earlier valid staged operations. A Python transaction context records a failed statement and raises on exit even if the caller caught the original error. `explain=True` does not execute or abort a transaction. If converting a native result to Python fails after execution, the preview closes the handle rather than claiming the already-executed mutation rolled back. In persistent mode an uncertain storage error poisons the writer; close/reopen and inspect before deciding whether to retry.

The SQL preview is not the complete relational architecture in the roadmap. Persistent mode adds bounded whole-model storage and recovery, but does not establish broad durability qualification. Concurrent readers, multiwriter semantics, and free-threading qualification remain absent. The bounded read-only natural-language interface is a separate unreleased slice and does not complete M2 or establish semantic quality; see [agent-query evaluation](agent-query-evaluation.md). The supported subset is not broad SQL support. SQL predicates and maintained filters use the same bound comparison primitive; SQL and maintained groups share checked-count/wide-sum aggregation. Both overlay and modular modes use these helpers, so reuse is not an overlay-only advantage or proof of a universal intermediate representation. Transactions extend a private candidate in place, discard it on failure, and persist canonical changes rather than replayable requests. A new maintained declaration computes its new derived relation state without copying existing source rows, subject to bounded declaration work and intermediate relations; subsequent statements propagate transaction-local effects without replaying cumulative derived changes, with the remaining scans and retained-state costs described above. Ad hoc SQL has no maintained query cache. Joins use nested loops; ordering materializes and sorts before applying `LIMIT`. `maintenance_steps` is a cumulative work counter, not a speed measure. Diagnostic counters and local comparisons do not by themselves establish an architectural or performance advantage. No claim here closes roadmap M1/M3/M4 or the separate migration, backup, concurrency, installed-artifact and broader qualification work.
