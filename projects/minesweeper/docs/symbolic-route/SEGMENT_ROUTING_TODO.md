# Segment Routing TODO

Partially implemented. The vendor-independent SID model, Cisco IOS Prefix/Adjacency-SID and
SRGB/SRLB parsing, guarded Prefix/Node/Adjacency SID database, canonical link dependency, and
incremental SID reconciliation are complete. The accepted ownership boundaries and staged plan
are recorded in `SR_ARCHITECTURE.md`.

SR must consume the stable guarded IGP topology produced by OSPF/IS-IS adapters. It must model
prefix/node/adjacency SID semantics separately from symbolic traffic execution and must not infer
SR reachability before the underlying guarded IGP state is available.

Ordered typed segment resolution, per-branch numeric stacks, and the vendor-independent SR policy/
segment-list/candidate-path model are implemented. Next: add the Cisco IOS vendor representation,
grammar, and normalized conversion, then guarded candidate selection/lifecycle and top-level output
acceptance. OSPF and additional vendor parser adapters remain independent follow-up work behind the
protocol-neutral underlay interface.
