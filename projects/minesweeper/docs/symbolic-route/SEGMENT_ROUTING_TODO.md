# Segment Routing TODO

Not implemented. The accepted vendor-independent architecture, ownership boundaries, parser audit,
identity rules, and staged implementation plan are recorded in `SR_ARCHITECTURE.md`.

SR must consume the stable guarded IGP topology produced by OSPF/IS-IS adapters. It must model
prefix/node/adjacency SID semantics separately from symbolic traffic execution and must not infer
SR reachability before the underlying guarded IGP state is available.
