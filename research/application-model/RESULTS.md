# Bounded qualification

This is a working volatile M0/M1 slice, not completion of either whole milestone.
No installed package API, durability, concurrency, optimization agent or competitive
performance claim is added.

## Executed locally

- Native unit/allocation-refusal suite: **66 assertions**, normal and ASan/UBSan.
- Integration suite: **11 tests**, including a nested **11-test** control/transport suite.
  The integration suite also passed against the ASan/UBSan-instrumented driver.
- Seeded differential coverage: both application declarations, seeds 0–3, 80 mutation
  batches per seed/domain, checking every source and derived bag and epoch after each
  accepted/rejected batch against Python recomputation and SQLite SQL views.
- Three compiled and executed faulty native variants were detected: omitted propagation,
  omitted absence dependencies, and premature publication before constraints.
- The Python example ran twice successfully without persisted-fixture collisions.
- Changed Python paths pass Ruff lint/format and Pyright standard checking.

Local native qualification used Apple Clang on macOS. ASan leak detection was disabled
because it is unavailable in this runtime; this is not a leak-sanitizer claim. Broader
repository and platform checks belong to the exact-head pull-request CI, not these local
counts. No package installation was performed for this qualification.

## Repairs driven by executed regressions

- Large-count self-join retraction now accumulates wide deltas before narrowing; a valid
  complete materialization is no longer rejected by an overflowing transient term.
- Scan counters include nonmatching visited rows and reset per successful commit.
- Caller mutation of nested declarations cannot change the oracle's model; SQL column
  tokens such as `c00` are compiled canonically as `c0`.
- Independent review reproduced a malformed-request hole: a later COMMIT could publish
  earlier staged statements. The driver now discards its staged batch on every rejected
  request. A seven-command regression tests malformed mutations, commit/snapshot tokens,
  repeated BEGIN and unknown commands, followed by a successful fresh transaction.

## Reproduce

From the repository root, with Python 3.11–3.14 and Clang:

```sh
python3 -m unittest discover -s tests -p test_application_model.py -v
python3 research/application-model/qualify_mutants.py
python3 examples/experimental_model.py
python3 examples/experimental_model.py
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  tests/native/test_model.cpp -o "$TMPDIR/refpot-model-tests-sanitized"
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 \
  "$TMPDIR/refpot-model-tests-sanitized"
clang++ -std=c++17 -O1 -g -Wall -Wextra -Werror \
  -fsanitize=address,undefined -fno-omit-frame-pointer \
  native/model/driver.cpp -o "$TMPDIR/refpot-model-sanitized"
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 \
  REFPOT_MODEL_DRIVER="$TMPDIR/refpot-model-sanitized" \
  python3 -m unittest discover -s tests -p test_application_model.py -v
```

## What this does not establish

The native implementation copies candidate state and uses matching scans. SQLite views
already provide consistent derived answers without handwritten propagation; this control
recomputes on read rather than maintaining materializations. Neither novelty nor speed
superiority is established. Generated incremental SQLite maintenance, pg_ivm and another
incremental platform remain required comparisons for broader claims. Recovery, concurrent
publication, efficient indexed preparation and bounded internal-agent experiments remain
future work.
