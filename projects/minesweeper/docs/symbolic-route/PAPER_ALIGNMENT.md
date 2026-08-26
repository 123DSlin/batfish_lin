# HoYAN / YU / tolerance symbolic-route alignment audit

## Scope

This audit concerns only symbolic route computation and the resulting guarded RIB. It does not
claim support for YU symbolic traffic execution or the tolerance paper's later per-device SMT seed
encoding and subspecification derivation.

The tolerance workflow explicitly keeps Step 1 (per-device SMT encoding) and Step 2 (symbolic
route computation) separate. A shared Z3 context is therefore not required for Step 2. Guard
compilation into a device encoding and the cross-model consistency condition belong to Step 3.

Within Step 2, all producers and consumers of link state must share one canonical link identity and
one polarity: an aliveness variable is true exactly when the link is up, while a failure budget
counts false aliveness variables. Connected-route availability, BGP-session propagation, and
forwarding-edge identity must refer to that same link component.

## Semantic mapping

| Paper concept | Implementation | Status |
|---|---|---|
| Route/message topology condition | `RouteGuard`, `SymbolicRouteMessage.guard` | Aligned |
| Candidate exists under a condition | `availabilityGuard` | Aligned |
| Candidate is selected after priority | `selectionGuard = availability AND NOT(higher availability)` | Aligned |
| Ingress policy | `SymbolicRouteIngressProcessor` plus Batfish BGP import transformation/policy | Aligned for current eBGP scope |
| Normal protocol precedence | Batfish `Rib` / `Bgpv4Rib` preference comparator | Aligned for connected/static and accepted IPv4 eBGP scope |
| Equal-preference candidates | Separate candidates; identical concrete contributions OR their availability | Aligned |
| Egress and link condition | Batfish BGP export pipeline, then `selectionGuard AND linkGuard` | Aligned |
| Propagation tree | `SymbolicRoutePropagationDependencies` | Aligned |
| Late higher-priority route | guard recomputation plus descendant withdrawal/re-advertisement | Aligned |
| Recursive withdrawal | dependency registry and convergence-engine withdrawal | Aligned |
| Convergence | FIFO work queue until no semantic delta | Aligned |
| `(device,prefix,path,attributes,guard)` branch | typed route, provenance path, and final selection guard | Aligned |
| Guard never mutates concrete attributes | immutable typed route plus separate guard | Aligned |
| `k`-failure pruning | not implemented | Required to complete tolerance Step 2 for a bounded failure domain |
| Route aggregation | not implemented | Missing outside the accepted example/scope |
| iBGP / IS-IS / OSPF / SR policies | TODO only | Not supported; never silently claimed |

## Guard interpretation required by tolerance

The implementation intentionally exposes two guards:

- `availabilityGuard`: the candidate route can be present after import;
- `selectionGuard`: the candidate is the selected route branch after excluding every strictly
  higher-priority candidate for the same router, VRF, and prefix.

The tolerance symbolic route branch must use `selectionGuard`. Using `availabilityGuard` as the
final branch guard would allow simultaneously selecting routes with different local preferences and
would disagree with Figure 4.

For later traffic execution, longest-prefix matching across different prefixes is a separate lookup
step. It must not be folded into control-plane BGP candidate selection.

## Four-router differential example

The snapshot under `networks/tolerance-symbolic-route/configs` is parsed by Batfish's Cisco parser
and converted to Batfish vendor-independent configurations. Prefix `P` is `10.0.0.0/24`; link-alive
The table below uses the paper's aliases: `a1=R1-R2`, `a2=R1-R4`, `a3=R1-R3`,
`a4=R2-R4`, `a5=R3-R4`. Executable output uses topology-derived stable names
`r1_r2`, `r1_r4`, `r1_r3`, `r2_r4`, and `r3_r4`; no numbered alias table is hard-coded.

The parsed R4 route maps assign local preferences 200 (R2), 100 (R1), and 50 (R3). The pipeline
produces exactly three R4 BGP candidates:

| Path | Availability | Selection |
|---|---|---|
| R1-R2-R4 | `a1 AND a4` | `a1 AND a4` |
| R1-R4 | `a2` | `a2 AND NOT(a1 AND a4)` |
| R1-R3-R4 | `a3 AND a5` | `a3 AND a5 AND NOT(a2) AND NOT(a1 AND a4)` |

These formulas are logically equivalent to Figure 4's `g2`, `g1`, and `g3`. All three branches
have a satisfying assignment with at most one failed link, so `k=1` pruning would retain all three.
The unpruned SRIB is therefore sufficient for this example.

## Remaining correctness boundary

The integration test uses Batfish parsing for configurations, routing policies, BGP processes, peer
objects, interfaces, and connected routes. The mapping from the five paper links to guard variables
and the five directed propagation edges is explicit test input. A future general upload adapter must
derive topology/session objects and apply a declared guard schema; it must not guess them.
