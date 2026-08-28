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

## Known boundary requiring later unification

The fixed-snapshot production path uses `BatfishBgpRedistribution`. The separate
`BatfishRoutingPolicyProcessor` / `BatfishRedistributionKey` / `BatfishRedistributionReconciler`
group implements an incremental lifecycle but is not called by the production pipeline. See
`PROTOCOL_PIPELINE.md`. Before incremental configuration changes are supported, both paths must
share one conversion/policy implementation or the unused incremental API must be removed.

## Review rules for future files

A new file is justified only when at least one condition holds:

1. it is a public extension point or stable result/input type;
2. it has multiple independent consumers;
3. it owns a stateful lifecycle that deserves isolated tests;
4. nesting it would create a circular or inverted dependency.

Otherwise, prefer a private nested helper inside the class that exclusively owns it.
