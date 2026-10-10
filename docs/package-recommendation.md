# RefPot package recommendation

**Status: proposed next implementation, not shipped.** The [retained findings](../benchmarks/random-updates/README.md) establish a promising update-only engine slice; they do not complete a general database package.

## First deliverable

Build an installable, independently usable custom embedded engine with durable create/read/update/delete and explicit transactions. Keep SQL parsing and the ORM out of the first package. Use one native execution core; SQLite remains a benchmark/differential-test comparator, never the RefPot backend. Choose the binding/build mechanism after checking lifetime, errors, GIL/thread semantics, build portability and installed-wheel behavior, not because a rewrite is assumed faster.

Support caller-provided records, not generated fixtures. Define the first value/key schema before implementing its format. Extend the measured storage design deliberately: inserts/deletes change immutable-image membership, sorted ordinal routing, dirty regions, checkpoint publication and redo replay. The existing update-only format cannot be relabelled as CRUD.

## Delivery gates

1. **Contract:** define key/value types, ordering, missing/duplicate behavior, overwrite semantics, transaction boundaries, read-your-writes, rollback, close, reopen, uncertain writes and supported single-writer/read visibility. Keep unsupported concurrency explicit.
2. **Native CRUD:** persist real records and membership changes; maintain atomic logical transaction identity; synchronize before acknowledgement; retain redo until replacement checkpoint state is durably published; reject unsupported formats/corruption. No fixture-derived reopening.
3. **Package:** canonical version via `uv version`; native build + `src/refpot/` interface, typed errors and context managers; source distribution and wheel build; no public tuning menu needed for basic usage.
4. **Installed-artifact tests:** isolated installation outside the checkout; runnable `examples/` for CRUD, commit/rollback and reopen; differential state-machine tests, repeated-key updates, duplicate/missing keys and aborted transactions; checkpoint/wrap/failure/restart tests against an acknowledgement ledger.
5. **Requalification:** benchmark the installed interface separately. Start with a bounded screening matrix and estimate runtime from executed pilots; expand only after correctness. Retain failures, matched SQLite durability/coalescing, setup/final-maintenance and p99/reopen/resource measures. Do not attach the old native ratios to the changed package.
6. **Documentation/CI:** update README, architecture diagram, website/Markdown exports and roadmap together; verify wheel/sdist contents, clean installs and examples on declared platforms. Release/PyPI publishing requires separate approval.

## After the engine package

- Add constraints and broader row/value semantics through the same execution boundary.
- Define and implement the SQL subset and structured-operation planner.
- Build the simple ORM only after the engine is independently useful and measured.
- Expand concurrency, recovery and resource qualification; define backup, format migration and release support.

The canonical [roadmap](../ROADMAP.md) remains the full product plan. No milestone is checked off merely because the experimental benchmark matrix passed. The architecture artwork still describes the planned SQL/ORM end state, not the currently measured slice.
