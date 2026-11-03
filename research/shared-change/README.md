# Shared-change native foundation experiment

This is a **volatile research component**, not a new installed RefPot API. It tests whether one
transaction-local signed change set can support candidate reads, relational maintenance,
final-state checks and prepared publication without copying affected committed relations.
It does not add SQL parsing, natural-language execution, persistence or concurrency.

## Run it

Python 3 and an existing C++17 compiler are required. Nothing is installed automatically.
Run from the repository root; each output directory must be new:

```sh
python3 research/shared-change/run.py --output "$HOME/.cache/refpot-shared-change/normal"
python3 research/shared-change/run.py --sanitize --output "$HOME/.cache/refpot-shared-change/sanitized"
python3 examples/experimental_shared_change.py --driver "$HOME/.cache/refpot-shared-change/normal/overlay"
python3 examples/experimental_shared_change.py --driver "$HOME/.cache/refpot-shared-change/normal/overlay" --publish
python3 examples/experimental_shared_change.py --driver "$HOME/.cache/refpot-shared-change/normal/overlay" --units 11
```

The example prepares a reservation, reads candidate availability while committed availability
is unchanged, then explicitly publishes or discards. The final command deliberately exceeds
capacity and must reject the entire transaction. Each invocation owns fresh volatile state.
The subprocess transport is research plumbing, not the proposed Python package interface.

`python3 -m unittest discover -s tests -p test_shared_change.py -v` builds both modes, runs the
qualification and comparison, and exercises both example outcomes twice from another working
directory. The sanitizer run disables leak detection where unsupported; it covers address and
undefined-behavior checks, not memory-leak qualification.

## What differs

Both modes use the same generic relational evaluator, definitions, integer/bag semantics,
dependency order and final-state constraints. Map, filter, union, join, group and anti join are
not implemented separately per domain.

- **Modular:** share untouched committed bags; copy each affected bag once; compute each
  affected node once; publish prepared replacement bags by nonallocating swaps.
- **Overlay:** retain canonical signed changes over committed bags; merge candidate visibility
  for reads and evaluation; preallocate new publication nodes; publish without allocations.

Preparation is private. `preview()` observes the prepared candidate; committed `snapshot()`
does not. `commit()` publishes the prepared result without rederivation. `rollback()` is
nonthrowing and idempotent. Preparation failures preserve committed state and leave the owner
usable. This is single-owner execution, not snapshot isolation or concurrent atomic publication.

## Evidence and decision

See [CONTRACT.md](CONTRACT.md) for the frozen semantic/workload scope and counter definitions,
and [RESULTS.md](RESULTS.md) for the complete comparison and limits. The runner saves raw matrix
records, source/binary hashes, compiler identity, qualification logs and derived comparisons.
It refuses to overwrite an earlier campaign and verifies source identity at completion.

The competent modular control already shares operators, catalog and delta evaluation. The
experiment isolates candidate-state materialization; it does not compare against whole-state
copying or full recomputation. Python recomputation and SQLite are independent correctness
controls, not package backends or timed competitors.

## Verdict: PARTIAL

The shared-change mechanism is executable and removes full affected-bag materialization in
this component. Dense changes increase merged-visibility work and retain almost as many
entries as the modular control. Fewer copied bag entries is neither a speed result nor a
measurement of total copying, allocations or peak memory.

Keep the overlay as a candidate implementation and the modular mode as its regression control.
Do not select it as a universal engine representation or claim originality: transactional write
sets and overlays are established mechanisms. The next useful slice is ordinary native query
execution and Python usability over this boundary, with ad hoc query lifetime separate from
maintained definitions. Durability, concurrency and SQL/NL frontend work remain separate gates.
