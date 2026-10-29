# Transactional model slice

An executable first slice of the self-maintaining engine roadmap: generic native
relations maintain two application models and reject invalid transactions atomically.
This is **experimental, volatile, single-threaded research code**, not the installed
`refpot.Database` API. The existing package API and storage format are unchanged.
It implements no optimization agent, inference, durability or concurrent access.

## Run it

Requirements: Python 3.11–3.14 and a C++17 compiler (`clang++` or `c++`; override with
`CXX` containing an executable path). No package installation, model provider or
third-party Python dependency is required.

From the repository root:

```sh
python3 examples/experimental_model.py
python3 -m unittest discover -s tests -p test_application_model.py -v
python3 research/application-model/qualify_mutants.py
```

The example compiles a standalone native executable into a temporary directory,
executes it through a small JSON-response/line-request harness, then cleans up.
Each returned row contains the declared integer columns followed by its bag
multiplicity. No sample output is prescribed: the example asserts the actual native
results and prints them. It can be run twice without persisted fixtures or collisions.

The Python context manager collects a whole transaction and submits it on normal exit.
An exception in the context submits nothing. Reads show committed state only; this
research helper is not the public package transaction API and does not expose staged
query results. The native core validates operations in order, then maintains and checks
the complete final candidate before publication.

## What runs

- `models.py` declares resources/teams/reservations and customers/products/orders using
  the same generic relational operators. Application code never updates a derived table.
- `native/model/model.hpp` owns source state, derived bags, delta propagation, constraints
  and atomic publication. There is no resource- or pricing-specific C++ branch.
- `native/model/driver.cpp` is a standalone test/example harness, not a new stable API.
- `native_model.py` compiles and drives that harness; it does not emulate relational execution.
- `oracle.py` recomputes every relation with Python integers from staged source state.
- `sqlite_control.py` compiles the same declarations to source tables and SQL views and
  validates the complete proposed model inside a SQLite transaction.

Read [CONTRACT.md](CONTRACT.md) for signed integers, bag semantics, checked expressions,
final-fit aggregate sums, source keys, final-state constraints and failure behavior.

## Why the SQLite control matters

SQLite views are already consistent with their source transaction. They need no manual
cache invalidation or propagation, and can enforce the same final-state rules through a
reusable caller. Therefore the example is **not evidence that SQLite cannot do this**.

The implementation distinction is materialization: the native slice propagates source
deltas into retained relational results; the SQLite control computes its view results on
read. Qualification compares every returned bag and accepted/rejected transaction, not
unmatched timings. No performance or novelty claim is made. A generated incremental
SQLite-maintenance control, pg_ivm and another incremental platform are still needed
before stronger comparative claims or broad M0 completion.

## Costs and limits

The first native correctness implementation prepares a candidate by copying state. It
reports that work alongside derived-node and row-visit counters. Delta execution is not
constant-cost commit, and matching scans are not indexed lookup guarantees. Shared
intermediate definitions can be reused by downstream relations; this is not yet automatic
physical-design synthesis.

The fragment has integers only, acyclic definitions, no NULL/text support and no arbitrary
Python computation cells. Model definitions are immutable. Definitions, malformed tokens,
wrong-width rows, duplicate/missing source keys, derived writes, overflow and invariant
failures must be rejected without partial committed state. Transport counts are bounded,
but this trusted local harness is not an adversarial resource-isolation boundary.

No process-restart recovery, durable representation migration, online plan activation,
free-threaded binding, inference, SQL frontend or ORM is implied. In particular, model
state is owned by the temporary native process and disappears when it closes.

## Qualification

The root test suite discovers `tests/test_application_model.py`. It compiles the native
harness, executes native unit/allocation tests and the control/transport suites, and compares
source and derived bags after deterministic and seeded transactions in both domains.
It also tests self-join multiplicities, anti-join absence, empty groups, final-fit aggregate
cancellation, unchanged-output propagation, caught invalid requests and Python rollback.

For an already built instrumented driver, set `REFPOT_MODEL_DRIVER=/absolute/path` to run
the same differential suite against it. Compile with `-fsanitize=address,undefined` and
`-fno-omit-frame-pointer` for sanitizer qualification; ordinary CI execution alone is not
a sanitizer or durability claim. Tests require a working compiler and fail rather than
silently skip the native path.

The mutant gate compiles and runs intentionally broken native copies: missing propagation,
missing anti-join absence dependencies and publication before constraint validation. It
requires an observed contract violation, not a compilation failure, for each mutant.

These are partial M0/M1 deliverables. Wider types, efficient indexes/state preparation,
full failure qualification, independent review and the roadmap's remaining competitor
controls must be distinguished from whatever this bounded test suite establishes.
