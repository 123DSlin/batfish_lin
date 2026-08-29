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
2. start continuous recursive next-hop-IP static reconciliation at the symbolic least fixed point;
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

`BatfishBgpRedistributionReconciler` continues the lifecycle from selected connected/static MAIN
branches into local BGP. It reuses `BatfishBgpRedistribution` for Batfish conversion and policy,
then drives typed `Bgpv4Route` contributions through the global BGP engine. MAIN withdrawal and
guard update therefore propagate through local BGP, remote BGP descendants, and remote MAIN before
the initiating engine call returns.

## Redistribution implementation boundary

The production pipeline has one redistribution path. `BatfishBgpRedistributionReconciler` discovers
the rule/source relationships, `BatfishBgpRedistribution` performs concrete Batfish conversion and
policy evaluation, and generic `BatfishRedistributionReconciler<Bgpv4Route>` owns contribution
lifecycle. A reentrancy barrier coalesces callbacks caused by the BGP-to-MAIN feedback edge; guard
logical equivalence is a true no-op, so a stable cycle terminates without synthetic updates.

The current rules intentionally select connected/static sources only. IS-IS-to-BGP redistribution,
live configuration/policy mutation, and conditional policy semantics remain out of scope and must
be added explicitly rather than inferred from this lifecycle.

## Recursive static lifecycle

`BatfishStaticRouteReconciler` observes each stable MAIN state. It excludes its own derived static
candidates, copies the remaining guarded candidates into a scratch MAIN RIB, and invokes
`BatfishStaticRouteResolver` to compute the least fixed point from a clean base. This prevents stale
recursive routes from sustaining one another after their real resolver disappears. Only logically
changed activation guards are applied back to production MAIN.

The scratch RIB recomputes MAIN preference and symbolic LPM from candidate availability; it does
not substitute a concrete `Rib.longestPrefixMatch` result for guarded LPM. Batfish's trie and static
activation helper remain the concrete semantic oracles inside each symbolic round. A reentrancy
barrier coalesces callbacks caused by static→BGP→MAIN feedback.
