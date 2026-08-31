# Segment Routing TODO

Partially implemented. The vendor-independent SID model, Cisco IOS Prefix/Adjacency-SID and
SRGB/SRLB parsing, guarded Prefix/Node/Adjacency SID database, canonical link dependency, and
incremental SID reconciliation are complete. The accepted ownership boundaries and staged plan
are recorded in `SR_ARCHITECTURE.md`.

SR must consume the stable guarded IGP topology produced by OSPF/IS-IS adapters. It must model
prefix/node/adjacency SID semantics separately from symbolic traffic execution and must not infer
SR reachability before the underlying guarded IGP state is available.

Ordered typed segment guard/endpoint resolution is implemented. Next: derive the ingress MPLS label
stack and per-hop SRGB/SRLB label interpretation without collapsing an index into one global label,
then add SR policy candidate selection. OSPF and additional vendor parser adapters remain
independent follow-up work behind the protocol-neutral underlay interface.
