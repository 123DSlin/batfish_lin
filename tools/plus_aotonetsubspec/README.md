# Auto Symbolic-NetSubspec

Symbolic tolerance subspecification pipeline. The input directory contains the
Minesweeper SMT encoding, structured symbolic RIB, and k-pruned symbolic routes.

## Preserved Plus baseline for versioned_results

The pre-optimization full-native Plus implementation is preserved separately in
`../plus_aotonetsubspec_versioned_20261125`. It restores the implementation used
for `DEMOIDEA/semantic_domains_20261125/versioned_results`: complete numeric
domains, the `regions` backend, per-fault Support and one solver process per
query, without device summaries or relational scopes. Both Demo1
`semantic_subspecs.txt` files were reproduced byte-for-byte, with 232 formula
equivalence checks per case. This is a reconstruction verified by reproduction,
not a claim of a historical byte-identical source snapshot.

Use that package's `run_preserved.py` entry point; it verifies frozen source
hashes before execution. Its `PRESERVATION.json` records provenance. Keep this
baseline independent of subsequent optimized Plus changes.

## Preserved original comparison methods

The original non-deterministic route-branch solver remains in `../netsubspec`:
Symbolic Route, device slice, branch seed, branch simplification and intersection.
Run its `tools/run.py` without `--property-preserving`. The original concrete-F
Traverse method remains separately in `../auto-netsubspec-Traverse`.
Neither method is replaced by Plus's finite `enumerate` backend.

Both source trees and their fixtures are frozen in the checksummed archive under
`../baselines/non_deterministic_routes_20261125`. See its
[preservation and replay instructions](../baselines/non_deterministic_routes_20261125/BASELINE.txt).
The snapshot includes existing working-tree edits. Keep original solving guards,
domains and traversal behavior separate from optimized Plus helpers so future
correctness comparisons retain their original implementation.

## Plus property-preserving mode

See the [Demo1 result index](example_results/README.md) for the two property variants
and their historical field-level and line-level subspecifications. Those saved
results use the legacy enumeration backend. See [the region solver contract](REGION_SOLVER.md)
for the current default backend, candidate scope and report schema.

Plus derives a subspecification from the reachability property compiled into the
input's Minesweeper export. Generate the input with the desired ingress, allowed
final nodes, destination, and physical-link budget. The first implementation
supports BGP-only single-path forwarding to one IPv4 /32. By default it
discovers the AS-path prepend statements in the export. For each statement it
derives a joint line-level formula and its field-level specializations. A
released prepend cost defaults to all nonnegative integers in the AS-path-length
abstraction, without an artificial maximum. Configuration
outside the target stays fixed for each projection.

From this directory, generate both kinds of subspecification for Demo1/Q1:

```bash
python3 -B tools/run.py ../../../DEMOIDEA/demo1/Q1/result/symbolic \
  --property-preserving --k 2 --consistency-workers 2 \
  --output /tmp/plus-q1
```

Use `--target` for a focused field query. Repeat it with enable and cost from
the same prepend statement for a focused line query. For a standard community,
select one encoded `set community` or community-list match value by its SMT
field name. The domain is one tag at a time from the export's exact standard
community index. Both field- and line-level files are written. The line-level
constraint also pins the other fields on the line to their original values.
See the [T3 and T4 examples](example_results/demo1_community_policy/README.md).
The output path must be new and outside the input.

Use `--all-configs` to cover every configuration field and statement encoded in
a supported Demo1 export.

```bash
python3 -B tools/run.py example_results/demo1_q1/input \
  --property-preserving --all-configs --k 2 \
  --output /tmp/plus-demo1-all
```

Full batch solves each encoded line with the other lines fixed, then specializes
the line result to each field with the other fields fixed. It reports missing
target domains as incomplete. Boolean fields use both values; community fields
use the export's encoded standard-tag index, an explicit model abstraction.
MED/local preference use the entire unsigned 32-bit domain. Prepend counts use
all nonnegative integers by default. IPv4 prefix-list statements use full 32-bit
network addresses and masks, lengths 0..32 and ordered ranges, with symbolic
constraints for contiguous masks and canonical network addresses. No sample
prefix list is chosen. `--cost-range` remains only as an explicitly requested
diagnostic restriction, never an automatic bound.

### Speclens source line and field granularity

Supply the original Cisco configuration directory to obtain source-command
contracts rather than one field per SMT variable:

```bash
python3 -B tools/run.py INPUT --property-preserving --all-configs --k 2 \
  --source-configs CONFIG_DIRECTORY --output NEW_OUTPUT
```

Without `--source-configs`, the legacy encoded-variable output remains available
for diagnostics. Frozen baseline packages and historical results are unchanged.
This option changes configuration locations, not Plus's all-legal-states
reachability semantics to the paper's stable-state-preserving semantics.

One CIDR, such as `5.5.5.5/32`, is one field (`prefix.addr`,
`prefix.length`). Its mask is derived. Explicit `ge` and `le` arguments are
separate fields; implicit endpoints follow command syntax. With no modifiers,
`start=end=prefix.length`. With only `le`, `start=prefix.length`. With only `ge`,
`end=32`. The compiler reads actual command text: `/32` and `/32 le 32` have
equal original endpoint values but different field structure.

Line contracts jointly vary a command's represented arguments while preserving
its syntax, existence, list name and sequence number. Field contracts fix other
source arguments and recompile derived values. Internal enable flags are not
source fields. A preserved prepend command requires a positive repetition
count; zero is an encoding no-op that would remove the command. Missing symbolic arguments, such as referenced list names, are
explicitly reported as limitations. Prepend supports repetition count of its
original ASN, not ASN replacement; communities retain the exported exact-index
abstraction. These outputs cover encoded policy commands, not every command in
the source configuration.

Already certified exact line regions can be reused without repeating network
projection:

```bash
python3 -B tools/adapt_speclens.py EXISTING_RESULT \
  --source-configs CONFIG_DIRECTORY --output NEW_OUTPUT
```

The adapter computes the deterministic inverse image of each **line** region
under the source-command compiler. It never combines scalar field results or
existentially releases other source fields. Source values and original
compilation are checked, with saved SMT equivalence and composition proofs.
The report records source locations, source hashes, constituent encoding
variables, compilation expressions and known limitations. In source mode the
text subspec files show the complete `Allowed` formula, including the legal
domain and model-support conditions. `empty` is used only when that complete
formula is `true`. JSON and `semantic_subspecs.txt` separately expose the legal
domain, property condition, support condition and full allowed formula.
Before presentation, complete `Allowed` formulas reuse the existing protected
reference simplifier and normalization rules. Proved constant bindings are
retained explicitly while simplifying the residual formula. Every accepted
shorter candidate must pass an unconditional XOR equivalence check; timeout,
unknown or a counterexample keeps the previous certified formula. This never
removes the legal domain merely because the property condition is true.
`*_raw.txt` and `raw_allowed_constraint` retain the unsimplified formulas and
`simplification` records byte counts and proof outcomes.
Commands whose source arguments have no symbolic encoding are displayed as
`NOT_PARAMETERIZED`, not `empty`; their argument edits have not been verified.

The region backend uses the complete native equations for each line, with
symbolic fault-coverage Support and candidate-scope certification. The explicit
enumeration oracle retains the former native-to-slice entailment checks.
Fields without an equation for their effects retain their full legal domain;
model Support requires their original value. This is recorded as a coverage
restriction, separately from the legal domain and property conditions.

Unbounded prepend solving requires regenerated inputs whose metric metadata
declares nonnegative internal BGP lengths and disabled overflow modeling. The
loader does not remove bounds from legacy SMT files. Regenerate those inputs
rather than interpreting a 16-bit encoding bound as a safety threshold.
Full IPv4 prefix solving also requires `0_encoding_semantics.json` declaring
`symbolic_prefix_length_ranges=variable-inclusive-bounds`. Older exports chose
equality versus range comparisons from the original rule; they must be regenerated.

Plus runs the existing semantic slicer and original-state consistency check.
The property backend loads the complete native equations once. Full batches
partition every non-pin assertion into device/shared relations and eliminate
private variables, retaining shared boundary symbols and the exported
reachability predicate. Each non-identity summary has an equivalence certificate;
a budget-exhausted module retains its exact original relation. The original selection guards serve the
consistency check. The property solve lets BGP compare its candidates with the
released configuration and symbolic failures.

The default `--property-backend regions` keeps target configurations symbolic.
It first checks reference-state existence and a candidate-scope gate on two
complete native models sharing the same faults. An originally invalid IMPORT
may become valid through a certified IMPORT or EXPORT policy change, including
downstream propagation and changes to a prefix-list shared by multiple policies.
Transfers are selected by their actual target dependencies after expanding
functional SSA helpers. A line's other fields remain in its joint domain; they
need not all appear textually in each transfer.

Certification checks source-field equations through encoded local origins and
proves each active transfer determines its output attributes. For every activated
IMPORT it then proves that activation is impossible if all relevant transfers
still satisfy their original-configuration policy at the current inputs. Fixed
configuration and destination context are identical in this counterfactual and
the main model. Missing equations, ambiguous attributes and uncaused activation
remain `UNSUPPORTED`. Attributes, winners and downstream
forwarding are recomputed and checked against the property; admission is not a
safety verdict. T4 now completes with only the recovered community value allowed.
Reports record `candidate_scope=CERTIFIED_POLICY_RECOVERY` and per-candidate
proofs in `policy_recoveries`, plus root transfer certificates and field
dependencies in `policy_transfer_roots`; unchanged candidate scopes retain `UNSAT`.

Counterexample faults guide exact Bad-region projection. Support retains symbolic faults: it first projects state existence to
`E(config,fault)`, then projects `Domain AND Budget AND NOT E` to missing-model
configurations. Its complement is Support; legal faults are not enumerated.
Reference coverage uses the same symbolic check and is cached across lines. The final output is
`Domain AND Support AND NOT Bad`; the backend never enumerates configuration
values. It certifies the final safety and Support conditions and saves each
projection's equivalence query before publishing a contract. Integer domains
are stored as interval metadata; `allowed_constraint` is the result API rather
than an array of accepted configurations. `property_condition` states the safety
restriction relative to `domain_constraint`; `model_support_condition` separately
states coverage. `semantic_subspecs.txt` displays these conditions and Allowed.
A type boundary in the legal domain is not a property-derived threshold.

`--max-coverage-checks` bounds Support projection work (the symbolic strategy
requires two projections; default limit 10,000), and
`--max-bad-regions` bounds counterexample iterations (default 1,000).
`--timeout` applies per query. Reports distinguish `PASS`, `UNSUPPORTED`,
`INCOMPLETE` and `ERROR`; failed targets do not publish an allowed formula.
Full batches can return partial results with explicit per-target statuses.
The contract is exact relative to the declared domain and supported encoding.
Full batches reuse a run-local solver process with scoped assertions, native
parsing, policy dependency indexes and reference coverage proofs. Every query
still has a standalone replayable file. `execution_reuse` reports actual reuse;
`device_summaries/device_summaries.json` records eliminated variables and any
identity relations. Branch consistency also uses symbolic fault coverage by
default: each seed projects model existence onto its link guards and proves
that no budgeted guarded fault is missing. Guard feasibility uses memoized
Boolean restriction instead of expanding fault sets. The consistency report
records `coverage_strategy` and `fault_assignments_enumerated`; the explicit
`--coverage-strategy enumerate` option of `2_consistency_checker.py` is a
regression oracle, never an automatic fallback.

Candidate and final-safety checks reuse certified relational scopes. The scope
walk follows complete state components, treating configuration and fault symbols
as shared inputs. Only disconnected state is eliminated, and its existence
frontier remains as an input constraint. `relational_scopes/*/scope_report.json`
records exact projection certificates and any identity fallback. This does not
claim to split a strongly connected routing component.

`--property-backend enumerate` preserves a finite-domain regression algorithm
for regression comparison. It enumerates target assignments, searches symbolic
faults for bad states, and checks every configuration/fault pair for Support.
Its coverage limit counts those pairs; it still refuses domains with model
coverage gaps. This backend and saved historical examples are not evidence
that the new candidate gate admits the same targets. Full `--all-configs` runs
require `regions`; the oracle cannot silently sample semantic domains.


Independent iBDP boundary and competition checks are available through
`tools/validate_regions.py`; see [the validation contract](REGION_SOLVER.md#independent-concrete-validation).

## Pipeline

### Runtime profiling

```bash
python3 tools/profile_runtime.py /tmp/netsubspec-0083/symbolic --k 2 \
  --workers 4 --consistency-workers 4 --check-failure-intersection \
  --traverse-results /tmp/netsubspec-0083/traverse
```

Alternatively add `--profile` to `tools/run.py`. Omit
`--check-failure-intersection` to profile only the official pipeline.
Each run is retained under `runtime_profile/<run-id>/`, with
`runtime_report.txt`, `runtime_report.json`, `runtime_events.csv` and stage
detail files. `runtime_profile/latest.json` points to the latest run.

`pipeline_wall_seconds` sums official symbolic stages, excluding optional validation.
Traverse is an independent pipeline. Its saved report separately records concrete
export, input preparation/AG, constraint solving, and intersection time.
`baseline_solve_and_intersection_wall_seconds` is Traverse solving plus intersection;
input preparation/AG and optional output comparison are excluded.
The optional check only reads completed outputs and runs equivalence queries.
It never enumerates failures or solves subspecs again.

The reports retain per-device consistency scopes, each seed's elapsed time,
each field/line's recorded duration, and Traverse per-F solver durations.
Times are elapsed wall time, not CPU time. Parallel task sums may exceed the
stage wall time; nested scopes, seeds and queries must not be added together.

Stage 1 remains serial because its shared SSA fixed-point closure needs a
separate independence audit before parallelization. Its per-device attribution
counts dependency-pass work and device audit/assembly/writing, while shared
parsing, indexing, root preparation, binding audit and process startup remain
explicitly shared/unattributed. No arbitrary division of shared cost is used.
Stage 2 supports device-level parallelism through `--consistency-workers`;
Stage 3 uses branch workers through `--workers`. Traverse uses F-level workers;
the optional output comparison parallelizes target equivalence queries.
Workers are configured upper bounds. Single runs are observations, not a
controlled scalability study or a direct full-pipeline speedup measurement.

From `tools/netsubspec`, prepare a fresh work directory with the 0083 exports.
The runner writes all stages into that directory.

```bash
mkdir -p /tmp/netsubspec-0083/symbolic
find ../../smts/smt_output_0083 -maxdepth 1 -type f -exec cp {} /tmp/netsubspec-0083/symbolic/ \;
```

Run the four stages in order:

```bash
python3 1_smt_slicer.py /tmp/netsubspec-0083/symbolic --k 2
python3 2_consistency_checker.py /tmp/netsubspec-0083/symbolic --k 2
python3 3_branch_simplifier.py /tmp/netsubspec-0083/symbolic
python3 4_branch_intersection.py /tmp/netsubspec-0083/symbolic
```

Or run the complete pipeline with the sequential symbolic runner:

```bash
python3 tools/run.py /tmp/netsubspec-0083/symbolic --k 2 --workers 4
```

The two independent pipelines for the validated 0083 BGP-only fixture are:

```bash
# From the Batfish repository root: inject each F, recompute iBDP, run the
# original Traverse scripts for line/field subspecs, then intersect across F.
python3 tools/auto-netsubspec-Traverse/run_traverse_baseline.py \
  --source smts/smt_output_0083 --network tolerance_sr_te_demo_bgp_x_b \
  --output /tmp/netsubspec-0083/traverse \
  --devices a,b,d,x --workers 4 --k 2

# From tools/netsubspec: existing symbolic-route pipeline (verification OFF).
python3 tools/run.py /tmp/netsubspec-0083/symbolic --k 2 --workers 4

# ON: after Stage 4, compare saved Traverse intersections with symbolic final outputs.
python3 tools/run.py /tmp/netsubspec-0083/symbolic --k 2 --workers 4 \
  --check-failure-intersection --traverse-results <absolute-traverse-run-directory>
```

The Traverse runner defaults to `tools/auto-netsubspec-Traverse/0_auto-netsubspec` for route analysis,
slicing, AG, and subspec solving. Cross-F aggregation uses the existing
`tools/auto-netsubspec-Traverse/intersect_failure_subspecs.py`.

The symbolic input remains the existing no-failure dataplane/symbolic-route export.
Stage 2 still checks all legal F; this consistency check is independent of the
optional subspec-output verification.

The optional check writes English `failure_intersection_check/report.txt` and
`report.json`. It compares every field/line target, grouped by configuration owner,
and references the original per-F constraints and failed links. Comparison reuses
the existing target bounds, keeps other fields fixed, and releases the target fields;
it does not assume the target fields retain their original values. Input hashes,
protocol/device scope, failure budget, and Traverse intersection hashes must match.
Missing targets, mismatches, errors/timeouts and residual route-state variables
cannot produce PASS. Completed symbolic Stage 4 outputs are retained on a failed
comparison. Validation time is excluded from both pipelines.
`failure_intersection_check_status.json` records whether this run enabled the check;
stale reports do not imply a check ran when the switch is off.

When the work directory also contains `smt_traffic_encoding.smt2`, derive the
failure-aware traffic-engineering subspecification after the control-plane
pipeline:

```bash
python3 tools/run.py /tmp/netsubspec-0083/symbolic --k 2 --workers 4 --traffic
```

The traffic stage can also be run independently:

```bash
python3 5_traffic_subspecification.py /tmp/netsubspec-0083/symbolic
```

The runner stops immediately if any stage fails. In particular, stages 3 and 4
cannot run after an incomplete or failed consistency check.

`--workers` controls stage-3 branch parallelism. When omitted, stage 3 uses up
to the available CPU count, capped by the number of branches. Workers only read
their branch seed and use isolated temporary directories; the main process
writes the combined reports in the original consistency-report order.

### 1. SMT slicer

Loads the full Minesweeper encoding once and computes one branch-independent
semantic slice per device.  A slice contains the device's import, protocol-best,
overall-best, and forwarding equations; every directly connected peer's export
toward the device; and the transitive configuration, failure, and SSA
dependencies.  Peer best-route records are declarations at the slice boundary
and are bound later by each branch seed.

After slicing, the exact `RouteBinder` used by Stage 2 audits every k-feasible
MAIN branch against the completed device slice.  Branch requirements never
enlarge the slice. Branches on the same device therefore reuse the same device
semantics; only their seed contexts differ. The global file is only the
deduplicated audit union of the device slices; later stages consume the
per-device files.

```text
1_sliced_device_smt_encoding/
  sliced_smt_encoding.smt2
  sliced_<router>_smt_encoding.smt2
```

### 2. Consistency checker

Builds one seed for every property-relevant, k-pruned MAIN branch and requires
all eligible branches to be `SAT` before subspecification calculation.
Forwarding states include selected `ROUTE` entries and an explicit `NO_ROUTE`
complement: the negation of the union of all covering MAIN selection guards,
computed before failure-budget pruning. A known device with no covering route
therefore has a no-route state with a true guard. It is checked with
`OVERALL_BEST.permitted=false`, the complete peer RIB boundaries (including
empty peer RIBs), and the original import/export and forwarding equations.
No selected import, predecessor, or invented route attributes are bound for
this state. Missing inputs or boundary declarations remain errors.

This gate proves coverage of **every legal F** represented by each seed, rather
than accepting a single satisfying failure assignment. It projects device state
from the seed while retaining all link guards, then proves that the branch guard
and fault budget imply the projected existence relation. No concrete fault sets
are enumerated by default. Projection failure or incomplete coverage fails the
gate; a missing-state witness is saved when one exists.
Reports retain `branch_kind` (`ROUTE` or `NO_ROUTE`) through branch projection
and final intersection provenance. `NO_ROUTE` seeds are projected normally;
their configuration constraints are not automatically treated as unrestricted.
The total branch count includes each device's potential no-route complement;
eligible counts exclude complements infeasible under the selected budget.

A selected static Null0 route is a `ROUTE` state, not `NO_ROUTE`. Its
`CONTROL-FORWARDING_<router>_null_interface` selection marker is bound to the
route guard; the original data-forwarding equations still discard the packet.
The independent Traverse input adapter preserves an inventoried Null0 failure
variable pinned to zero as local interface state rather than enumerating it
as an inter-router physical link.

```text
2_consistency_check/
  seeds/<router>/seed_<branch>.smt2
  consistency_report.txt
  consistency_report.json
```

### 3. Branch simplifier

Computes line-level constraints first and specializes each line by fixing its
other fields to their original values. IP and mask stay a paired field target.
A field is solved directly when its target-dependent route snapshot release
differs from the line's release.

The solver takes one symbolic seed/AG per branch. It substitutes a singleton
destination and eliminates redundant binary integer link variables using the
seed's Boolean-to-integer bridge equalities and integer bounds. The remaining
symbolic scope is eliminated exactly, without enumerating concrete failures,
then AutoNetSubspec's `simplify -> propagate-values -> solve-eqs ->
ctx-solver-simplify` chain simplifies the resulting configuration goal.
Temporary unary applications preserve the released fields through `solve-eqs`.
The stage keeps all competitors and fails if a result retains internal state.
The optional Traverse comparison checks the final results independently.

Use `--workers N` (or `-j N`) to cap concurrent branch calculations.
The JSON and text reports in `3_branch_subspecs/` retain the seed hashes, guard,
released route observations, and line/field provenance.

The optional verifier now consumes the independent Traverse pipeline output:

```bash
python3 ../auto-netsubspec-Traverse/compare_traverse_results.py <symbolic-work-directory> \
  --traverse-results <traverse-run-directory> \
  --output <symbolic-work-directory>/failure_intersection_check/report.json
```

This performs only output equivalence checks. It does not generate additional
concrete-F subspecs. The old projection oracle is no longer in the pipeline.

### 4. Branch intersection

Within each verification router, intersects all branch-local formulas for each
field or configuration-line target. The output distinguishes the verification
router from the configuration owner and preserves every contributing branch.

```text
4_final_subspecs/
  final_subspecs.txt
  final_subspecs.json
  <router>/
    field_level_subspecs.txt
    line_level_subspecs.txt
```

Every simplified intersection is checked for exact equivalence using an
`UNSAT` disagreement query. Integer output retains meaningful configured
thresholds, such as `local-pref < 200` rather than `local-pref <= 199`.

### 5. Traffic-engineering subspecification

The traffic SMT encoding already contains the control-plane forwarding branches
inside its symbolic load expressions. Stage 5 substitutes away the auxiliary
load variables, universally quantifies the encoded failure variables under the
failure budget, and eliminates those variables separately for each link-capacity
property. It then intersects the link-local projections into an exact joint
constraint over all selected SR candidate-path weights.

The stage also derives one localized slice per weight by pinning every other
weight to its original value. Both every link projection and the final
intersection are accepted only after an `UNSAT` disagreement check.

```text
5_traffic_subspecs/
  traffic_subspecs.txt
  traffic_subspecs.json
  joint_weight_subspec.smt2
```

See [`docs/SYMBOLIC_CONSISTENCY_DESIGN.md`](docs/SYMBOLIC_CONSISTENCY_DESIGN.md)
and [`docs/SYMBOLIC_SUBSPEC_REUSE_AUDIT.md`](docs/SYMBOLIC_SUBSPEC_REUSE_AUDIT.md)
for the formal construction and reuse boundary.


## Protocol-adapted device slicing

Stage 1 dispatches through `slicing.ProtocolSliceAdapter`. Default `bgp`
preserves the existing command line and byte-identical BGP outputs:

```bash
python3 1_smt_slicer.py WORK_DIRECTORY --k 2 --slicing-protocol bgp
python3 tools/run.py WORK_DIRECTORY --k 2 --slicing-protocol bgp
```

This flag selects the slicing strategy, not the generation protocol switch.
It does not filter or rewrite the input encoding or symbolic RIB. Matching
run-level generation scope remains necessary. Mixed-protocol composition
cannot be implemented by simply concatenating independently generated slices.

| Component | Responsibility |
| --- | --- |
| `1_smt_slicer.py` | normalization, indexing, common configuration/failure/SSA closure, structural audits, output |
| `slicing/base.py` | adapter and per-run assertion-rule interfaces |
| `slicing/models.py` | device boundary and branch audit data |
| `slicing/bgp.py` | existing BGP topology boundary, ownership, directional/single export rules and RouteBinder audit |
| `slicing/registry.py` | explicit dispatch; unknown/mixed protocols are errors |
| `slicing/isis.py` | reserved IS-IS interface; rejects before output generation |

Adapters supply `required_input_files`, `build_scopes`, `build_requirements`,
and `create_rules`. Rules supply `should_remove`, `assertion_owners`, and
`dependency_keys`. Generic `protocol_equation_symbols` identify retained
protocol roots; the compatibility property `incoming_export_symbols` exposes
BGP roots for existing callers. Scope/adapter identities must agree.

IS-IS is not implemented. Its adapter must define SPF/L1/L2, prefix origins,
distances, ECMP, recursive dependencies and MAIN-RIB boundaries before enabling.
`--slicing-protocol isis` (also `IS-IS`/`IS_IS`) errors without overwriting
existing slices. A test-only protocol confirms that the shared engine accepts
non-BGP equation roots and inputs; it is not an IS-IS approximation.

## Symbolic RIB query indexes and bounded caches

`consistency/branch_loader.py` now constructs immutable posting lists for router,
VRF, exact prefix, plane and protocol. Exact queries inspect the smallest
posting list, preserving the original candidate-id order. Destination queries
look up every ancestor prefix in a per-scope network index (IPv4 and IPv6),
including default routes, all same-prefix candidates and shorter fallbacks.
This is a lookup optimization, not longest-prefix pruning or guard filtering.

Per-RIB LRU caches reuse queries, parsed prefixes, predecessor lookup and the
complete device/peer RIB context shared across branch seeds. They are bounded:
entry/forwarding/context/predecessor queries 2048 each, scope indexes 512,
parsed route prefixes 4096 and destination networks 1024. Eviction discards
only derived results, never source routes. `query_cache_info()` exposes cache
statistics; `clear_query_caches()` releases cached results. A new RIB instance
must be loaded when source inputs change.

## Tests

From `tools/netsubspec`:

```bash
python3 -m unittest discover -s tests
```

Set `NETSUBSPEC_RUN_0083` to the directory containing completed `symbolic` and
`traverse` runs to exercise their integration tests. Set
`NETSUBSPEC_CONCRETE_0083` to the exported `failures_AT_MOST_K_k2` directory to
exercise exact failure coverage and SMT pinning.
