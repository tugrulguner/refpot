# Shared-change foundation: first discriminating experiment

Status: planned experiment contract, frozen before comparison results. This is a bounded
native research slice of M0/M1, not completion of either milestone and not a new installed
package API. Existing package and prior native model sources remain unchanged.

## Question and competing implementations

Can a single transaction-local change representation serve candidate-state reads, relational
maintenance, final-state constraint checking and publication without repeatedly copying
unmodified rows? Does the benefit survive a modular control that already shares a catalog,
operators, maintained results and one evaluation per changed derived node?

Both implementations use the same generic typed relation declarations and delta evaluator:

- `modular`: privately materialize only affected relations, copying a touched committed bag
  once; reuse untouched relations and atomically publish prepared replacements.
- `overlay`: keep committed bags with canonical signed row changes; read the merged candidate
  state, derive dependent changes and check constraints through that state. Prepare all
  publication resources before any committed mutation, then publish the row effects.

The historical native model's whole-state copying is a secondary reference, not the strong
comparison. Full recomputation is a correctness oracle, not a speed baseline. SQLite views
provide an independently executed semantic control, not a matched incremental speed control.

Transaction write sets, overlays, delta maintenance and copy-on-write are established
mechanisms. A win here selects a useful component; it does not establish original engine
architecture or justify a universal representation. Both modes already share logical meaning.
The experiment isolates state/change handling rather than attributing its effects to NL or AI.

## Supported semantics and lifecycle

Use the existing application-model contract: immutable acyclic definitions; signed 64-bit
integers; map/filter/equijoin/anti-join/group/union; bag multiplicities; primary-key source
operations; checked expression arithmetic and final-fit grouped sums. No SQL parser, NULL,
strings, ad hoc plan binding, policy engine, concurrency, durable storage or model provider.

1. Construct the declared graph and initialize source rows.
2. Prepare an ordered mutation batch. Derive each affected relation once and validate every
   required-empty relation against the complete final candidate. Temporary violations can be
   repaired later in the same batch. Invalid source operations reject the entire batch.
3. Inspect candidate results while ordinary reads still expose committed state.
4. Explicitly publish or discard. Publication must not recompute the graph or allocate.
5. Failed preparation, failed requests and discard leave committed bags and epoch unchanged.
   No hidden replay, inference or automatic retries. Successful no-op commits advance epoch
   consistently with the original research contract.

Candidate inspection is a research snapshot export and may copy complete output bags.
Those serialization/export copies must not be concealed as eliminated engine work. Shared
visibility does not establish snapshot isolation, durability or correct human intent.

## Frozen qualification and workload matrix

- Independent Python full-recomputation oracle and SQLite control for both resource allocation
  and pricing/order models. Compare every source/derived bag and epoch after accepted and
  rejected batches, including continued use after rejection.
- Source insert/update/delete, repeated writes to one key, delete/reinsert, canceling changes,
  no-op, constraint rejection, final-state repair, foreign references and arithmetic overflow.
- Self-join cross terms, bag duplicates, absence dependencies and disappearing groups.
- Prepared preview versus committed reads, rollback and explicit publish. Malformed transport
  must invalidate pending/prepared work; a subsequent publish cannot commit earlier effects.
- Seeded sequences, four seeds per domain and eighty mutation batches per seed, including
  invalid inputs. The fixed seeds select test data, not model behavior.
- Native allocation-failure enumeration during prepare; after each failure require old state,
  old epoch and successful subsequent use. Refuse allocation during successful publication.
- Normal and ASan/UBSan builds. Leak qualification is separate where unavailable.

For component cost comparison, use both domains, populations 32 and 256, and five scenarios:
read-only inspection, canceled source update, sparse quantity update, dense quantity update,
and broad parent change (capacity in resources, price in pricing). Run both modes over
identical declarations/data/operations and compare full outputs independently. Retain records
for every matrix cell; do not drop unfavorable dense or no-op cases.

Record definition/source identity, compiler/platform, source/derived rows, affected nodes,
operator row visits, row copies, delta entries, publication effects and candidate state where
available. Distinguish counters' logical units from heap bytes and include construction and
inspection costs in the report. No wall-clock speed, throughput, memory-byte or database-wide
superiority claim is authorized by these work counters. Timing needs a separate calibrated,
paired and repeated campaign after correctness and counter audit.

## Counter interpretation

`copied_rows` counts complete committed bag entries copied into private candidate materializations.
It is not a count of every row-vector copy. `delta_key_copies` counts key insertions through the
signed-change accumulator; join-wide intermediates and constructed expression rows are not
included. `source_lookup_row_copies` counts source rows detached before editing their delta.
`staged_insert_rows` counts additional publication nodes prepared by the overlay. Modular
candidate nodes already exist in its materialized bags. `retained_candidate_rows` includes
visible materialized entries, delta entries and staged insertion entries; it excludes container
metadata, bytes and transient evaluation storage and is not peak memory.

`rows_visited` counts logical visits in the shared operator evaluator. `visibility_entries`
counts physical base/delta entries consumed by candidate scans, exposing overlay merge work;
point-lookup comparisons, constructor binding and map rebalancing are not counted. Publication
row effects are logical changed tuples, not identical physical operations (modular publication
swaps bags). Every matrix record includes initialization counters and two full-state exports,
whose row counts are separate from transaction counters. Preview/snapshot serialization still
copies output rows. Neither fewer bag copies nor fewer retained entries proves lower total cost.

## Decision

Select overlay handling as a candidate component only if full-state and failure oracles pass
and the measured reduction in copied state survives the strong modular control. Report dense,
unchanged-output and rollback costs, and identify work not removed (including joins/group scans).
If a competent modular overlay can reproduce the benefit, record that equivalence rather than
calling integration an invention. Do not resolve NL output format, general storage architecture,
permissions, runtime conflict detection or recovery from this experiment.
