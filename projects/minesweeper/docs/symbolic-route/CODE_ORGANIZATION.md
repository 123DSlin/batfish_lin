# Symbolic Route Code Organization

## Naming and file rules

This package follows one public top-level type per file. Small implementation-only types belong in
their sole owner's file; independent public concepts remain separate even when their source files
are short.

Names retain `SymbolicRoute` when the type is a public engine API and retain `Batfish` when the
type delegates concrete protocol semantics to Batfish. These prefixes are intentional ownership
markers, not removable repetition. Private or package-private helper names should be short because
their owner already supplies the context.

## Types consolidated into their owner

- `SymbolicRouteConvergenceEngine.WorkItem`: private advertisement/withdrawal queue item. No other
  component may schedule or interpret it.
- `SymbolicRouteIngressProcessor.PreparedCandidate`: package-private policy result used by the
  convergence engine to validate contribution-to-candidate identity before installation.

## Public types that remain separate

- Guard model: `RouteGuard`, `Z3RouteGuard`, `Z3RouteGuardFactory`.
- Route identity/model: `SymbolicRoute`, `SymbolicRouteKey`, `SymbolicRouteContributionId`,
  `SymbolicRouteMessage`, `SymbolicRouteProvenance`, `SymbolicRouteSeed`, `SymbolicRouteSession`.
- Guarded RIB API: `GuardedRib`, `GuardedRibEntry`, `GuardedRibDelta`, `GuardedRibUpdate`,
  `GuardedRibUpdateType`.
- Protocol extension API: `SymbolicRouteProtocolAdapter`, `SymbolicRouteIngressPolicy`,
  `SymbolicRouteEgressPolicy`, `SymbolicRouteKeyFactory`, `SymbolicRouteMessageIdFactory`.
- Engine API: `SymbolicRouteIngressResult`, `SymbolicRouteConvergenceEngine`,
  `SymbolicRouteConvergenceResult`, `SymbolicRoutePropagationDependencies`, `SymbolicRouteNetwork`,
  `SymbolicRouteNetworkFactory`.
- Link/failure API: `LinkFailureKey`, `TopologyLinkGuards`, `LinkAvailabilityAssignment`.
- Batfish pipeline API: `BatfishSymbolicRoutePipeline`, `BatfishSymbolicRoutePipelineInput`,
  `BatfishSymbolicRoutePipelineResult`, `BatfishParsedSnapshotPipelineInputBuilder`.
- Batfish IS-IS boundary: `BatfishIsisEdge`, `BatfishIsisProtocolAdapter`, and
  `BatfishIsisTopologyAdapter`. These remain separate because they respectively own parsed edge
  identity, Algorithm 2 import/export semantics, and topology/seed conversion.
- IS-IS level lifecycle: `BatfishIsisLevelTransitionReconciler` owns the persistent mapping from
  selected L1 candidate identity to derived L2 contribution identity. It is intentionally separate
  from the protocol adapter and generic convergence engine.
- Cross-protocol lifecycle: `BatfishMainRibReconciler` owns stable protocol-plane candidate to MAIN
  contribution identities and the semantic diff that converts protocol RIB stable states into
  MAIN advertisements, guard updates, replacements, and withdrawals.
- Redistribution lifecycle: `BatfishBgpRedistributionReconciler` scans stable MAIN candidates and
  owns whole-network rule/source identity; generic `BatfishRedistributionReconciler` applies each
  typed Batfish policy result to the target RIB without knowing configuration or rule discovery.
- Static lifecycle: `BatfishStaticRouteResolver` remains the pure Batfish-backed symbolic LPM/fixed
  point operation; `BatfishStaticRouteReconciler` owns persistent MAIN observation, scratch least-
  fixed-point reconstruction, and semantic delta application.

Merging these public types would hide lifecycle boundaries, produce large files, or force callers
to use deeply nested names without reducing semantic complexity.

## Logical package groups

The current source level needs package-private access between several engine components, so a
physical subpackage move is deferred. The intended dependency direction is nevertheless:

```text
guard/model
    -> guarded RIB
    -> convergence engine
    -> protocol-neutral network
    -> Batfish protocol adapters
    -> parsed-snapshot pipeline
    -> report view
```

If physical subpackages are introduced later, use these groups:

- `symbolicroute.guard`: guard interface and Z3 implementation;
- `symbolicroute.rib`: guarded RIB entry/delta/update types;
- `symbolicroute.engine`: messages, ingress/export, dependencies, convergence, network assembly;
- `symbolicroute.batfish`: static, BGP, policy, topology, and failure adapters;
- `symbolicroute.pipeline`: parsed input, top-level runner, result, and report record.

Such a move must be a dedicated mechanical commit after public/package-private boundaries are
explicit. It must not be mixed with route semantics changes.

The protocol-to-MAIN path is unified behind `BatfishMainRibReconciler`; MAIN-to-BGP uses
`BatfishBgpRedistributionReconciler`. Both initial and incremental paths therefore call the same
`BatfishBgpRedistribution` conversion/policy implementation. See `PROTOCOL_PIPELINE.md`.

## Review rules for future files

A new file is justified only when at least one condition holds:

1. it is a public extension point or stable result/input type;
2. it has multiple independent consumers;
3. it owns a stateful lifecycle that deserves isolated tests;
4. nesting it would create a circular or inverted dependency.

Otherwise, prefer a private nested helper inside the class that exclusively owns it.
