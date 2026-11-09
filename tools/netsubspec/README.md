# Auto Symbolic-NetSubspec

Symbolic tolerance subspecification pipeline. The input directory contains the
Minesweeper SMT encoding, structured symbolic RIB, and k-pruned symbolic routes.

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
This gate checks **every legal concrete F** represented by each seed, rather
than accepting a single satisfying failure assignment. Its exhaustive check
is separate from the symbolic subspecification solver in stage 3.

```text
2_consistency_check/
  seeds/<router>/seed_<branch>.smt2
  consistency_report.txt
  consistency_report.json
```

### 3. Branch simplifier

Computes line-level constraints first, following the scheduling in
`tools/auto-netsubspec-Traverse/0_auto-netsubspec/4_subspec_simplifier.py`, then specializes each line by fixing
its other configuration fields to their original values. IP and mask stay a
paired field target. A specialization is reused only after proving it exactly
equivalent to the existing field-specific symbolic projection; otherwise stage
3 falls back to that direct field projection.

Stage 3 uses the current seed/AG as the input to the reference-style main
solver path. It reuses `simplify -> propagate-values -> solve-eqs ->
ctx-solver-simplify` and the existing configuration/dependency extractor.
Target-dependent route snapshot release is unchanged. Temporary unary parameter
applications protect target fields from `solve-eqs` and are restored before proof.

For guarded attribute assignments that ordinary propagation cannot eliminate,
`utils/util_reference_seed.py` exposes the existing policy and route-candidate
conditions as conditional value expressions. It retains the entire source
constraint body and every candidate guard. Configurations are not substituted;
released attribute observations are excluded. Inactive-value choices are only
candidate witnesses: acceptance always requires exact equivalence against the
unchanged symbolic problem. Cycles and oversized expansions are skipped safely.

Residual integer route state rejects the candidate. A small residual problem
with at most 16 internal Boolean state symbols may be reduced with its symbolic
failure/destination environment; this does not enumerate concrete F or rerun
full device-state QE. Errors, remaining state or unproved equivalence retain the
original staged projection as a correctness fallback. Line audits expose the
adapter, substituted-value count, residual sizes, acceptance and attempt time.
Accepted results use derivation `symbolic-reference-simplification`.

The 0083 seed-first run uses 22 existing domain proofs and 17 reference-derived
line results, with no full-device staged-projection fallback. Its 166 branch/final
results are equivalent to the previous implementation. Independent Traverse
verification still reports the same two constraint differences and four residual
state outputs; equivalence to Traverse is not claimed.

Failure variables remain symbolic; no concrete failure assignments are
enumerated and no intersection across different branches occurs here. For a
branch `b`, configuration target `T`, and legal failures `F(b,k)`, the intended
meaning is `S(b,T) = AND over f in F(b,k) of S(b,T,f)`. The universal failure
quantifier expresses this intersection symbolically; it is not a concrete-F
solver loop or an extra network-wide verification task.

The symbolic adapter retains the existing destination scope, complete peer
candidate context and target-dependent release of observed route attributes.
Literal reuse of all old route-value observations would freeze a changed LP
to its original value. These semantics therefore cannot be replaced with the
reference's concrete-route input preparation unchanged.

Use `--workers N` (or `-j N`) to cap concurrent branch calculations.

```text
3_branch_subspecs/
  branch_subspecs.txt
  branch_subspecs.json
  <router>/
    field_level_subspecs.txt
    line_level_subspecs.txt
    branch_subspecs.json
```

The projection reuses AutoNetSubspec's configuration domains, normalization,
IP/mask grouping, and output format. A normalized result is accepted only after
an exact symbolic equivalence check. Structured output retains branch guards,
seed hashes, route-attribute bindings, and atom-level constraint provenance.
Field audits include `source_line_group` and `field_source`, distinguishing
proved line specialization from direct field fallback.

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
