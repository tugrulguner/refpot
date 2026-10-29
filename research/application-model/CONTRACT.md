# Transactional model slice: executable contract

This is an experimental, volatile M0/M1 engine slice, not a new installed RefPot API.
The existing Database/Row API and storage format are unchanged. No durability,
concurrency, arbitrary Python callbacks, SQL frontend, model inference or optimizer
agent is provided by this slice. No speed or originality claim follows from it.

## Data and definitions

A model is an immutable, topologically ordered list of named relations and a list of
relations required to be empty after a transaction. Names match `[a-z][a-z0-9_]*`.
Every cell is a signed 64-bit integer; booleans are not integers in the Python API.
No NULLs, strings or floating point. Rows are ordered tuples. Source column zero is
the primary key; derived relations use bag semantics, with positive signed-64-bit
multiplicities. Returned bags are sorted by complete tuple, not insertion order.

Declaration JSON (Python dictionaries; CLI transport is separately defined):

- `{"name": ..., "op": "source", "width": N}`: N is positive.
- `{"name": ..., "op": "map", "input": ..., "exprs": [["c0"], ["c1", "c2", "-"]]}`:
  postfix expressions of integer literals, column references `cN`, and `+`, `-`, `*`.
  Each expression leaves exactly one integer. Each arithmetic operation is checked;
  equivalent-looking reassociation is not allowed to change overflow behavior.
- `{"name": ..., "op": "filter", "input": ..., "column": N, "cmp": "lt", "value": 0}`:
  comparisons `lt`, `le`, `eq`, `ne`, `ge`, `gt` against an integer literal.
- `{"name": ..., "op": "join", "left": ..., "right": ..., "left_key": N, "right_key": M}`:
  equijoin; concatenate complete left and right rows; multiply multiplicities.
- `{"name": ..., "op": "anti", "left": ..., "right": ..., "left_key": N, "right_key": M}`:
  left rows with no equal right key; preserve left multiplicities, ignoring right count
  beyond presence. Missing parents can therefore be constrained transactionally.
- `{"name": ..., "op": "group", "input": ..., "key": N, "value": M}`:
  output `[key, sum(value * multiplicity), count]`, one row per present group.
  Empty groups disappear. Sum uses a wide intermediate and final signed-64-bit check;
  count and multiplicities must fit signed-64-bit. Overflow rejects the transaction.
- `{"name": ..., "op": "union", "left": ..., "right": ...}`: bag union, equal widths.

References must point to preceding definitions; unknown parents, duplicate names,
invalid widths/columns/expressions or malformed protocol requests are errors. Initial
state is empty; constant zero seed rows are supplied by mapping source tables.
Source and derived definitions cannot be edited after construction.

## Transactions

A batch is an ordered list of `insert`, `update`, `delete` operations on source relations.
Insert/update carry the complete row; update must name an existing primary key (change a
key via delete+insert). Delete carries a primary key. Missing update/delete and duplicate
insert are errors. Derived writes are forbidden. Operations see earlier operations in
the same batch. An invalid operation rejects the entire batch; no partial state is exposed.
In the line protocol, any rejected request discards the active staged batch. A later
COMMIT cannot publish its earlier statements; begin a new batch before retrying.

After staging all source changes, propagate through the graph in topological order,
then check every required-empty relation against the complete candidate state. This
permits a temporary violation in statement order to be repaired later in the same batch.
Uncaught arithmetic/constraint errors reject source, derived and maintenance state together.
All successful batches (including empty/no-op batches) advance an unsigned-64-bit epoch;
rejected batches preserve epoch and all state. Epoch exhaustion rejects without changes.

Read only committed bags. A native snapshot holds an immutable copy whose contents survive
later commits. The slice is single-threaded and process-local. A Python transaction context
batches operations; it does not promise intermediate derived reads or package API parity.

## Native algorithm and cost boundaries

Propagate signed source deltas; transform deltas through map/filter/union; handle joins with
`delta_left join old_right + new_left join delta_right` so simultaneous changes and self-joins
include cross terms exactly once. Reevaluate only touched groups and affected anti-join keys.
Indexes or scans used to locate matches must be stated and counted honestly.

For this first correctness slice, copying candidate bags/metadata before evaluation is
allowed and must be reported as whole-state preparation work. Atomicity is one final
nonthrowing swap; no in-place publication followed by fallible allocation. This is NOT
constant-cost commit, persistence, concurrent MVCC or an established performance advantage.

## Controls and qualification

Use a Python-integer full-recomputation oracle independent of native delta algorithms.
Use a compiler from these declarations to SQLite source tables, derived SQL views and
final-state checks in one SQLite transaction. Views are a competent no-stale-state baseline:
they need no application-written propagation, but compute derived answers on demand instead
of maintaining native materializations. State that distinction; do not claim behavior is
impossible in SQLite or manufacture a speed headline from unlike maintenance policies.

Demonstrate resources/teams/reservations and a second pricing/order model using the same
operators, not domain-specific C++. Verify full source/derived bags and epoch after every
accepted/rejected batch, including updates/deletes, foreign references, join duplicates,
self-joins, group disappearance, arithmetic boundaries and final-state repairs. Add native
allocation-failure tests and ASan/UBSan execution. Comparison with pg_ivm and another
incremental platform, general types and broad performance qualification remain later M0/M1
work, not completed by the SQLite control.
