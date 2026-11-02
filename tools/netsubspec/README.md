# Auto Symbolic-NetSubspec

Symbolic tolerance subspecification pipeline. The input directory contains the
Minesweeper SMT encoding, structured symbolic RIB, and k-pruned symbolic routes.

## Pipeline

Run the four stages in order:

```bash
python3 1_smt_slicer.py symbolic_output_0010 --k 1
python3 2_consistency_checker.py symbolic_output_0010 --k 1
python3 3_branch_simplifier.py symbolic_output_0010
python3 4_branch_intersection.py symbolic_output_0010
```

Or run the complete pipeline with the sequential symbolic runner:

```bash
python3 tools/run.py symbolic_output_0010 --k 1 --workers 4
```

When the work directory also contains `smt_traffic_encoding.smt2`, derive the
failure-aware traffic-engineering subspecification after the control-plane
pipeline:

```bash
python3 tools/run.py symbolic_output_0010 --k 1 --workers 4 --traffic
```

The traffic stage can also be run independently:

```bash
python3 5_traffic_subspecification.py symbolic_output_0010
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

```text
2_consistency_check/
  seeds/<router>/seed_<branch>.smt2
  consistency_report.txt
  consistency_report.json
```

### 3. Branch simplifier

Projects every checked symbolic branch directly to field- and line-level
configuration constraints. Failure variables remain symbolic; no concrete
failure assignments are enumerated and no branch intersection occurs here.

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
