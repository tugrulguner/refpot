# Bounded agent-query preview: evaluation evidence

This page records a small frontend-selection experiment for the unreleased read-only
agent-query slice. It does not establish natural-language reliability, broad SQL support,
or an engine advantage. The committed product direction remains first-class natural-language
querying (roadmap M2); M2 is not complete or qualified by this evidence.

## Scope and result

A paired screen compared SQL-plus-bindings generation with structured query components
lowered to SQL, both using RefPot's native binder and executor. This was not a direct native-IR
or parser-bypass comparison. The repaired v2 replay produced 12 matching native query results
across both frontends combined: three supported tasks × two data fixtures × two frontends.
Each frontend matched all six of its supported-query results against an independent SQLite
oracle. Eleven compiler/preflight/replay tests passed. The captured SQL response key and null
optional component fields needed replay-harness repairs; those repairs made no additional
model calls. Version 1 had incomplete capability prompts, a compiler defect, and three outputs
exhausted their completion budgets. Its evidence is retained separately, not pooled with v2.

The paired campaign used 24 model calls, with a total provider-reported cost of $0. V2 used
four developer-authored tasks and two data fixtures; these were not held-out intent judgments.
On its unsupported `AVG` task, the SQL frontend declined, while the components frontend
returned an object without a valid action. Checking each captured action against two fixtures
does not make it two independent model decisions. V1 included one ambiguous request, but
neither screen establishes ambiguity reliability, paraphrase stability, schema-change handling,
provider-failure robustness, or general semantic quality.

The supported-query fixture scores tie. SQL plus bindings was selected provisionally because
the SQL frontend handled the unsupported task correctly in this small screen and requires less
compiler maintenance. This is not a universal advantage, reliability result, or evidence that
generated SQL captures user intent. Keep both frontends' failures and limitations visible when
extending the corpus; binder acceptance and matching rows do not establish arbitrary user intent.

Raw evaluation artifacts are retained outside this repository at
`~/.hermes/refpot-research/agent-readonly/frontend-comparison/parent-review.json`.
They are not committed here and no public artifact URL is claimed.

## Current preview boundary

The source preview requires explicit `agent=True`, caller-supplied configuration, and an
explicit disclosure setting before schema metadata can be sent to a generator. The configured
Python generator is trusted caller code: it may be slow, block, or perform its own side effects;
RefPot cannot sandbox or preempt it and makes no hard-deadline claim. Only relation names and
output columns are disclosed, never rows, view definitions, private inputs, or database
revision. The native binder independently enforces the allowlisted relations, read-only SQL
subset, schema freshness, and handle/transaction ownership. This constrains query authority;
it does not prove that the query means what the user intended.

M2 remains unchecked. Novel questions and paraphrases, ambiguous and unsupported requests,
schema changes, provider failures, human-held-out tasks, and broader risk/coverage and silent-
assumption measurements remain open. The present fixture is a protocol demonstration, not a
semantic-quality or deployment claim. The implementation is not included in published 0.1.2
or any published wheel.
