# Symbolic Route Protocol Pipeline

## Implemented flow

```text
Batfish connected/static typed route
  -> Batfish static activation and main-RIB preference
  -> Batfish routing policy
  -> Batfish convertNonBgpRouteToBgpRoute
  -> guarded local BGP seed
  -> Batfish BGP pre-export transformation
  -> Batfish BGP export policy
  -> Batfish BGP post-export transformation
  -> symbolic session/link guard propagation
  -> Batfish BGP import transformation
  -> Batfish BGP import policy
  -> guarded receiver BGP RIB
```

Batfish owns concrete route transformations, policy interpretation, and route preference. The
symbolic route layer owns availability/selection guards, contribution identity, dependencies,
withdrawal, and stable state. Minesweeper SMT consumers must encode the resulting guarded state and
must not run another control-plane convergence simulation.

## Current BGP scope

- IPv4 unicast typed as `AnnotatedRoute<Bgpv4Route>`;
- connected/static redistribution through Batfish conversion and routing policy;
- directed eBGP export/import pipeline;
- session link guard propagation and stable contribution identity;
- receiver/VRF-scoped Batfish `Bgpv4Rib.comparePreference` delegation, using that VRF's concrete
  main RIB and `BgpProcess` tie-break/multipath configuration;
- session-scoped opaque advertisement identity derived from the stable sender candidate key, never
  from `route.toString()`;
- strict session endpoint and sender/receiver VRF validation.

The adapter calls Batfish's iBGP/route-reflection branches because they share the same helpers, but
iBGP route-reflector, multipath/add-path, conditional IGP-cost tie-breaking, confederation, and
dynamic session-change scenarios still require dedicated acceptance tests before being declared
complete. The current oracle is exact only for the supplied fixed concrete underlay. If IGP
reachability or next-hop cost is itself guarded, the comparison must be lifted over guarded IGP
state; one concrete main RIB must not be treated as complete symbolic BGP best-path semantics.

Identical concrete candidates arriving through different parent contributions are deliberately
stored as separate contribution IDs and OR-combined in one guarded candidate. The dependency
registry retains every parent, so withdrawing one parent removes only its contribution. A concrete
route replacement creates a new candidate identity; the Stage 3.4 replacement lifecycle withdraws
the old contribution and descendants before installing the new identity.

## Stage 4.5 one-shot whole-network runner

`BatfishSymbolicRoutePipeline.run(input)` now executes one fixed normalized snapshot in this order:

1. converge guarded connected and non-recursive static main-RIB seeds;
2. resolve recursive next-hop-IP static routes to a symbolic fixed point;
3. apply configured Batfish redistribution policies to selected connected/static candidates;
4. originate guarded local BGP candidates;
5. run directed IPv4 eBGP export, link-guard, import, and dependency propagation to convergence;
6. return every router/VRF main-RIB and BGP-RIB candidate in one deterministic report.

The report exposes plane, router, VRF, prefix, protocol, next hop, concrete route attributes,
availability guard, selection guard, contribution IDs, and router path. It can be queried as
`router -> VRF -> entries` or serialized as pretty JSON. Every configured router/VRF is present,
including an empty list for a RIB with no candidates. Route text is output-only and is never used
as an advertisement identity.

The current input is deliberately typed and normalized: Batfish `Configuration` objects, concrete
receiver/VRF main-RIB contexts, guarded route seeds, recursive static routes, redistribution rules,
directed `BatfishBgpEdge` objects, and symbolic sessions. Raw uploaded configuration parsing and
automatic guard assignment belong to the next adapter layer, after the accepted configuration and
guard schema is specified. Unsupported iBGP/OSPF/IS-IS/SR input must not be silently accepted.

## Protocol RIB to MAIN lifecycle

`BatfishMainRibReconciler` registers stable-state listeners on the IS-IS L1, IS-IS L2, and BGP
networks. It uses `(protocol plane, SymbolicRouteKey)` as source identity and a private stable
contribution ID for MAIN; route text is never an identity. A selected source branch becoming
unsatisfiable or disappearing withdraws its MAIN contribution recursively, a logically changed
guard updates the same contribution, and a changed concrete route is handled as replacement.
Connected and static routes remain native MAIN seeds and are not owned by this reconciler.

This lifecycle stops at MAIN. A post-return MAIN change does not yet trigger fresh redistribution
into BGP because the production MAIN-to-BGP conversion remains the fixed-snapshot path described
below. This boundary does not affect the initial complete symbolic RIB, but it must be resolved
before configuration/policy changes are supported incrementally across redistribution.

## Redistribution implementation boundary

There are currently two deliberately distinct redistribution paths:

1. The fixed-snapshot production pipeline calls `BatfishBgpRedistribution` while constructing its
   initial local BGP seeds. This path computes one stable Symbolic RIB from an empty state and is
   the path exercised by `BatfishSymbolicRoutePipeline.run`.
2. `BatfishRoutingPolicyProcessor`, `BatfishRedistributionKey`, and
   `BatfishRedistributionReconciler` implement and test an incremental advertise/deny/withdraw/
   atomic-replacement lifecycle. They are not called by the current fixed-snapshot pipeline.

Keeping both paths permanently would risk semantic drift (for example next-hop, `nonRouting`, or
missing-policy behavior). Until incremental configuration/policy updates are in scope, the direct
fixed-snapshot BGP path remains the only production entry. Before incremental updates are enabled,
the two paths must be unified behind one conversion/policy implementation rather than exposed as
parallel production APIs.
