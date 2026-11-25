# Configuration region backend

Property mode defaults to `--property-backend regions` with automatic semantic
numeric domains. It uses the native
expanded SMT equations, with only the original counterexample request removed.
It releases the requested configuration pins and retains route competition,
export/import, forwarding and the shared physical fault budget.

```bash
python3 -B tools/run.py example_results/demo1_c_only/input \
  --property-preserving --k 2 --output /tmp/plus-regions \
  --target Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_enable \
  --target Config_t_RoutingPolicy_FROM_ISP__Seq20__Line2__prepend_aspath_cost
```

Use a fresh output directory. Existing inputs and historical results are not
modified. `--property-backend enumerate` retains the former finite-domain solver
as a regression oracle, including its former refusal of model-coverage gaps.
The oracle is for explicitly bounded regression tests, not full semantic-domain
solving or an automatic fallback. `--all-configs` rejects it.

MED/local preference use unsigned 32-bit integers; prepend uses nonnegative
integers without an artificial upper bound. These are formulas, not selected
values. An explicit diagnostic `--cost-range` is marked as a restriction.
Complete IPv4 prefix syntax is symbolic, including mask/length consistency,
canonical network bits and ordered ranges. Communities remain scoped to the
export's encoded tag abstraction, rather than a newly claimed encoding of all
real standard-community values.
Full-prefix native exports must declare `variable-inclusive-bounds` in
`0_encoding_semantics.json`. Original exact/range shape must not select the
comparison operators after configuration fields are released. Legacy exports
must be regenerated; their constraints are never silently rewritten.

## Contract and execution order

Let `h` be the released configuration, `F` physical faults and `S` internal state.
All other configuration fields remain at their original values. `D` is the
requested domain, `B` is the fault budget and `P` the exported reachability
predicate. The exact contract relative to the input encoding is:

```text
Bad(h)     = D(h) AND exists F,S: B(F) AND M(h,F,S) AND NOT P(h,F,S)
Support(h) = D(h) AND forall F: B(F) => exists S: M(h,F,S)
Allowed(h) = D(h) AND Support(h) AND NOT Bad(h)
```

1. Build reusable exact device/shared relations for full batches, eliminating
   only partition-private variables; keep cross-device correlations. Keep an
   identity relation if local projection exceeds its budget. Certify reference
   state existence for all symbolic budgeted faults, caching the proof across
   configuration lines.
2. Compare directed BGP IMPORT validity in two complete model copies sharing
   the same fault, over the entire requested domain. If a record becomes valid,
   identify IMPORT/EXPORT transfers that depend on released fields, expanding
   functional SSA helpers. Other line fields remain constrained by the joint
   domain rather than being required in every transfer. Check source-field
   equations through encoded local origins and prove active transfer attributes
   are uniquely determined by that transfer alone. Construct an old-policy
   counterfactual at the current inputs, with the same fixed configuration and
   destination as the main model. Prove each activated IMPORT requires changed
   behavior in a certified transfer in its source closure. Reject incomplete
   sources, ambiguous transfers and activation without such a change.
3. Check the current single-path forwarding scope over the released domain.
4. Query uncovered bad states with symbolic configuration and faults. Fix the
   complete counterexample fault assignment and eliminate state to obtain an
   exact bad region. Accumulate regions until the global query returns UNSAT.
5. Project `E(h,F) = exists S: D(h) AND M(h,F,S)`, retaining configuration
   and physical faults. Project `Missing(h) = exists F: D(h) AND B(F) AND NOT E(h,F)`.
   Support is `D AND NOT Missing`. The default does not enumerate fault assignments;
   the former per-fault strategy remains an explicit Python regression option.
6. Certify final safety, domain containment, Support implication and formula
   composition. Every projection is separately checked against its original
   existential formula. Reject residual state symbols, helpers and quantifiers.
7. Publish `allowed.smt2` only after all required proofs succeed.

The directed IMPORT identity does not certify preservation of full AS paths,
origins or end-to-end path identities. The model is currently BGP-only, one
IPv4 /32 with IGP modeling disabled. Native equations provide a complete
reference within that encoding; SMT proofs do not establish real-protocol
correctness independently of the encoding. Independent recomputation remains
an external validation layer. Traffic, ECMP and certified performance slicing
are not introduced by this change.

## Implementation and failure handling

- `solver_session.py` / `region_context.py`: scoped persistent solver queries,
  run-local native/index caches and content-addressed reference proof reuse.
  Timeout/error destroys the session. Standalone query files remain replayable.
- `consistency/symbolic_coverage.py`: existential seed projection onto link
  guards and an UNSAT uncovered-fault proof, including non-vacuity and missing
  state witnesses. Guard feasibility uses memoized Boolean restriction. The
  explicit exhaustive checker is retained only for regression comparison.
- `relational_scopes.py`: exact candidate/safety scopes over full connected
  state components. Shared configuration/fault inputs do not propagate the scope
  walk. Only the disconnected remainder is sent to QE; its existence frontier
  is retained. A structural separation check plus the frontier equivalence
  certificate justifies the composed scope. Competitors inside a kept component
  are never pruned, and failure falls back to the exact identity relation.
- `device_summaries.py`: nonduplicating native assertion partitions and certified
  existential relations, retaining shared variables and property observables.
  This reduces private state; it does not assert that all device coupling or
  strongly connected BGP dependencies have disappeared.
- `region_smt.py`: bounded solver operations, strict goal parsing, symbol
  hygiene, separate proof queries and saved query metrics. QE uses
  `simplify qe-light qe2 simplify`; it does not use `solve-eqs` on free targets.
  Mixed Int/BV target equivalence uses a bounded portfolio on the same theorem.
  Timeouts remain evidence; only a successful UNSAT certificate permits output.
  Query metrics record the successful certificate and every attempted tactic.
- `configuration_domains.py`: complete typed numeric domains and coupled IPv4
  syntax, expressed as constraints rather than sample assignments.
- `property_regions.py`: compact domains, native model selection, gates, Bad
  projection and symbolic fault-coverage Support. `range` domains stay intervals, including
  metadata and field-domain membership checks.
- `candidate_recovery.py`: IMPORT/EXPORT policy recovery and downstream
  causality checks, source equation coverage and transfer self-composition.
  `policy_recoveries` records sources, attributes, origins and causality proofs;
  `policy_transfer_roots` records root transfers and actual field dependencies.
  This is an encoding-relative check of existing records, not a mechanism for
  inventing missing prefixes, sessions or policy statements. Source advertisements
  may change; certification does not freeze the original winners or attributes.
- `property_subspec.py`: backend dispatch and existing report integration.
  Field subspecs specialize a verified line formula with other fields pinned
  to their original values; they never existentially quantify those fields.

`PASS` means exact completion, even if the allowed region is false.
`UNSUPPORTED` means the requested candidate/protocol scope was not certified.
`INCOMPLETE` means a limit, timeout, UNKNOWN or proof failure prevented completion.
`ERROR` means an input/tool execution error. Batch reports retain per-target
failure statuses and publish contracts only for completed targets.

`--max-coverage-checks` bounds Support projections (two for symbolic regions); for
the legacy oracle it bounds assignment/fault pairs. `--max-bad-regions` bounds
Bad iterations. There is no claim of polynomial fault or QE complexity.

`support_cases` contains one symbolic `E(h,F)` relation by default, with
`failures=null` and `strategy=symbolic`; it is not a per-fault array.
`reference_support_evidence` links the original symbolic totality certificate,
including cache-hit provenance. `fault_assignments_enumerated=0` describes the
property backend. The Plus branch-consistency stage now independently proves
symbolic coverage of each original seed, also without concrete fault traversal.
Its report has separate coverage-strategy and enumeration counters. Original
reference seeds and guards are unchanged; they do not constrain property solves.

Every invocation saves numbered SMT queries and solver logs in `region_evidence/`.
`region_report.json` records success/failure, domain, Bad, Support, witnesses and
phase/query metrics. Integers use interval metadata rather than enumerated
`allowed_configurations`; clients should read `allowed_constraint`. Missing
Support is separately reported as a formula, not described as operational
unsafety. Encoding metric bounds can restrict the supported configuration domain.

## Verification and performance experiments

```bash
python3 -B -m unittest discover -s tests
python3 -B tools/benchmark_regions.py \
  example_results/demo1_c_only/all_configs/input \
  --output /tmp/plus-region-benchmark --repeats 3 \
  --wall-timeout 60 --query-timeout 15
```

The benchmark tests cost maxima 10, 100, 1000 and 65534 with enumeration, direct
QE and fault-guided regions. All three first run the same reference Support,
candidate and single-path gates on the native model. The benchmark oracle
classifies unsupported assignments so that its Allowed contract matches the
region backend. Successful outputs are compared by XOR/UNSAT queries.

Each case runs in its own process group with a wall limit that terminates its
solver children. A separate oracle coverage limit prevents unbounded Python
assignment materialization. Timeouts and resource exclusions remain INCOMPLETE.
Reports include environment/input hashes, total and phase times, check/query
counts, projection counts, formula size, final output bytes and peak individual
worker/solver RSS (not simultaneous process-tree memory). Single-run timings
are preliminary; repeat serially on controlled hardware for research claims.

## Independent concrete validation

`tools/validate_regions.py` mutates disposable copies of a known one-AS prepend
statement, invokes the local Batfish `smt_tests` launcher, and recomputes iBDP
RIBs for every fault within the budget. It never reads SMT output to construct
concrete next hops. It requires a prepared case with `configs/`, `problem.json`
and its exported model input. Configuration hashes must match the manifest.

```bash
python3 -B tools/validate_regions.py \
  --case example_results/demo1_q1 --case example_results/demo1_c_only \
  --output /tmp/plus-independent-audit
```

This historical bounded regression tool samples disabled prepend and enabled
costs 0, 1, 2, 65532, 65533 and 65534 within its explicitly restricted 0..65534
test domain. These samples neither define nor prove the production semantic
domain or its subspecification. Disabled prepend and
cost=0 both omit the real command; their distinct symbolic assignments are
validated separately against the same concrete export. The input stanza must
contain exactly one expected ASN. Specify router, policy, sequence and SMT
field names explicitly for another supported prepend fixture.

The adapter validates exact fault-universe coverage, uses longest-prefix
matching, rejects ambiguous/ECMP best routes, and treats loops, missing routes,
wrong endpoints and null routes as failed delivery. For every sampled
configuration/fault it checks both state existence and whether *all* modeled
states match the independently observed physical forwarding and property.
Per-fault Support predictions and final Bad/Support/Allowed membership are
checked separately. A good path cannot hide another modeled bad state.

An encoding without a state is recorded as `OUTSIDE_MODEL_SUPPORT`, not an
operational failure. The audit returns `PASS_WITH_SUPPORT_GAPS` when all checks
agree but some samples fall outside the encoded Support region. It returns
`FAIL` for coverage gaps, forwarding/property disagreement, wrong projection
membership, malformed output or a failed export. A successful sample audit is
not a proof of real-protocol correctness over every configuration value.

The local iBDP launcher must already be built, normally at
`batfish/bazel-bin/projects/allinone/smt_tests`. Each export saves its launcher
hash, configuration hashes, process status and log. Concrete and symbolic
artifacts remain in separate directories. Process groups are bounded by
`--export-timeout`; solver queries by `--query-timeout`.

The first fresh audits, using the legacy metric-bounded exports, found:

- Demo1's sampled supported boundaries agree with Q1 and C-only contracts.
- At enabled costs 65533 and 65534, iBDP still delivers safely in both problems,
  while some fault scenarios have no state in the SMT encoding. These costs
  are excluded by Support, not by observed operational failure.
- Demo3's four sampled configurations, each under 46 faults, preserve the
  property while allowing changed competition and downstream propagation.
- A synthetic nonmonotone configuration domain requires two distinct bad-fault
  projections and contains a separate Support hole. CEGAR, direct QE and the
  pointwise oracle agree; a one-region resource cap publishes no partial result.

See the workspace `DEMOIDEA/plus_region_projection_20261124/round2_independent/`
for raw exports, logs and validation summaries. These are sample-based audits,
not performance measurements or a general closure proof for route identities.


## Counterexample-guided terminology

The benchmark label `cegar` denotes counterexample-guided **region projection**
in this implementation. Each counterexample is obtained directly from the
complete model. It selects a complete fault assignment for exact QE over the
internal state; the resulting configuration region refines the remaining
candidate region. The final uncovered-bad-state UNSAT query certifies coverage.
The code does not currently construct an abstract transition system or classify
spurious abstract traces, as in classical CEGAR. See [Clarke et al.'s original
CEGAR paper](https://www.cs.cmu.edu/~emc/papers/Conference%20Papers/Counterexample-guided%20Abstraction%20Refinement.pdf).

The division of work is:

- Counterexample guidance chooses the fault and controls region accumulation.
- QE computes the exact bad configuration region at that fault.
- Support separately certifies model existence under every budgeted fault.

This avoids outer configuration-value enumeration. Runtime still depends on
fault/region structure and projection difficulty. Current Demo1 measurements
show direct `qe2` and guided projection performing similarly.

## BGP metric domain correction

New native exports model internal BGP AS-path length and BGP-only overall BEST
metrics as nonnegative integers, without the former artificial 16-bit ceiling.
A prepend of 65534 followed by more session hops can therefore remain
representable. Negative lengths remain excluded. External environment metrics
retain their explicit bound below 256; other IGP/mixed-record domains retain
their existing bounds. The separate optional `model_overflow` semantics remain
unchanged. Mixed IGP/BGP BEST records still need a future conditional-domain
extension; Plus currently accepts BGP-only inputs.

`0_metric_domains.json` records these assumptions. Plus validates its schema,
copies it into fresh CLI inputs, hashes it, and includes the policy in reports.
Legacy inputs without this file are marked `unannotated-export`; their actual
SMT constraints remain authoritative and are never rewritten by the loader.
Regenerate inputs with the corrected encoder to obtain the corrected domain.

The re-exported Demo1 contracts over 0..65534 have Support equal to the entire
requested domain. Q1 allows both enable values throughout that domain. C-only
requires enable=true and cost>=1. Eight symbolic XOR checks certify the expected
Bad/Support/Allowed regions and preservation of prior results through 65532.
Fresh iBDP checks include 65533 and 65534 and find no remaining Support gaps in
the checked configurations. Older experiments and fixtures remain unchanged.

With freshly generated Bazel test launchers, select a compatible Java runtime
(e.g. JDK 17) with `--java-binary /path/to/jdk17/bin/java`. Java 25 cannot run
this launcher's Security Manager setup. The concrete adapter supplies the
`java.lang` module opening required by the legacy parboiled parser, and records
the selected runtime in each export's execution metadata.
