# Absence-aware full-state transaction control

This is an isolated research runner. It does not modify or supersede the frozen
`research/sql-maintenance/matched.py` v2 replay. The correctness oracle replays
source operations into its own dictionaries; it never constructs expected state
from rows read back out of either backend.

## Correctness run

```sh
python3 research/transaction-deltas/runner.py --engine sqlite
python3 -m pytest tests/test_transaction_control.py -q
```

The SQLite control has a primary-key index on `dimension.id`, an explicit index
on `fact(dimension_id)`, and real insert/update/delete triggers maintaining
`maintained(dimension_id, SUM(amount), COUNT(*))`. `projected` is an ordinary bag
view. `missing` is an ordinary, indexed anti-existence view:

```sql
CREATE VIEW missing AS
SELECT f.id AS id, f.dimension_id AS dimension_id
FROM fact AS f
WHERE NOT EXISTS (SELECT * FROM dimension AS d WHERE d.id = f.dimension_id)
```

At transaction commit, SQLite evaluates the equivalent final empty assertion
and rolls back the entire transaction on violation. The native adapter declares
the requested materialized-view grammar and a required-empty assertion around
that same relation. Source tables intentionally have no foreign key so absence
is represented by the `missing` relation rather than blocked at the source.

Each construction, source statement, ordinary error, final commit/rejection,
and rollback is checked against all source and derived bags: `dimension`, `fact`,
`maintained`, `projected`, `missing`, plus an ordinary join read of `fact` against
`maintained` as `derived_rhs`. Cases cover temporary missing state
repaired in-transaction, rejected missing commit, missing state rolled back,
source deletes/reinserts, duplicate projection rows, derived aggregate state,
last-member group deletion, and an ordinary duplicate-key error aborting its
prefix. Tests inject both an omitted source operation and rollback-as-commit and
require the independent oracle to catch each.

The native backend is an adapter for the unreleased installed `refpot.sql`
preview. Candidate installed wheel and sdist runs are recorded in [RESULTS.md](RESULTS.md)
and `evidence/qualified.json`. To reproduce with an installed candidate, run:

```sh
python3 research/transaction-deltas/runner.py --engine native-overlay
python3 research/transaction-deltas/runner.py --engine native-modular
```

## Bounded timing/RSS screen

Run the sparse and dense/cancellation service cells with SQLite only:

```sh
python3 research/transaction-deltas/runner.py --performance \
  --engine sqlite --repeats 3 --rows 256 \
  --output research/transaction-deltas/raw/sqlite-screen
```

Or, when the installed native candidate supports this control:

```sh
python3 research/transaction-deltas/runner.py --performance \
  --engine all --repeats 3 --rows 256 \
  --output research/transaction-deltas/raw/paired-screen
```

Every trial is a fresh subprocess. Setup, full-state validation and close durations are reported separately. Setup and full-state validation are outside
the `service_ns` interval; the interval includes all transaction updates and
commit/assertion validation. The sparse cell updates one indexed source row. The
dense cell updates half the fact rows twice in one transaction, returning the
source bag and group totals to their original values. SQLite and native use the
same parameterized point-update sequence (SQLite caches prepared statements; native parses each call), logical data, transaction boundary and
final-state oracle. The order of sparse/dense cells and engines alternates by repeat. These
few repeats are a screening artifact, not a qualification campaign.

Raw JSON is written per trial in the selected output directory; stdout contains
the combined raw records and medians. RSS uses
`resource.getrusage(RUSAGE_SELF).ru_maxrss`, normalized to **bytes** (macOS value
is bytes; Linux value is KiB converted to bytes), with the platform and baseline
peak recorded. This is process high-water RSS, not peak incremental memory
attributable only to service, total allocations, copy volume, or native work
counters. Setup is excluded from elapsed service timing, not from process RSS.

Use a fresh output directory; existing trial files are never overwritten. Pass
`--require-installed` for artifact qualification: it rejects editable/source package origins.
The default 256-row screen stays within the native nested-loop declaration/query budgets;
large workloads may be refused, and are not silently downscaled.

The [bounded findings](RESULTS.md) include native losses and all raw records. They
are a short service/RSS screen, not a broad performance conclusion. The native absence path was not in the
old baseline, so the old baseline is not treated as comparable. Retain raw records
and provenance before making any cross-engine claim.
