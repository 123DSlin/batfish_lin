# Segment Routing TODO

Partially implemented. The vendor-independent SID model, Cisco IOS Prefix/Adjacency-SID and
SRGB/SRLB parsing, guarded Prefix/Node/Adjacency SID database, canonical link dependency, and
incremental SID reconciliation are complete. The accepted ownership boundaries and staged plan
are recorded in `SR_ARCHITECTURE.md`.

SR must consume the stable guarded IGP topology produced by OSPF/IS-IS adapters. It must model
prefix/node/adjacency SID semantics separately from symbolic traffic execution and must not infer
SR reachability before the underlying guarded IGP state is available.

Ordered typed segment resolution, per-branch numeric stacks, the vendor-independent SR policy/
segment-list/candidate-path model, and the Cisco IOS explicit MPLS SR-TE parser/conversion path are
implemented. Guarded SR-policy candidate selection and stable-snapshot lifecycle are also complete:
candidate availability and selection remain distinct, equal-preference candidates coexist, and
dependent forwarding contributions are replaced or withdrawn as SID/underlay state changes. Next:
add top-level output and parser-driven acceptance. Dynamic/PCEP candidates, adjacency segment-list
syntax, OSPF, and additional vendor parser adapters remain independent follow-up work behind the
protocol-neutral underlay interface.
