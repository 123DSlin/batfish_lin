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
implemented. Guarded SR-policy candidate selection and stable-boundary lifecycle are also complete:
candidate availability and selection remain distinct, equal-preference candidates coexist, and
dependent forwarding contributions are replaced or withdrawn as SID/underlay state changes.
Top-level pipeline integration, deterministic readable/raw/JSON output, and parser-driven IOS
acceptance are complete. Dynamic/PCEP candidates, adjacency segment-list syntax, recursive
Binding-SID segment expansion, OSPF, and additional vendor parser adapters remain independent
follow-up work behind the protocol-neutral underlay interface. Ordinary typed Prefix/Node/Adjacency
SID bindings are already supported.

Stage 7.9 is not a prerequisite for the current symbolic-route/SR correctness closure. It is a
configuration-compatibility extension to schedule only when required by an experiment: IPv4
address-based Prefix/Node segments are needed for the existing `traffic_demo` syntax, while parsed
adjacency segments and recursive Binding-SID expansion broaden supported configurations further.
Experiments restricted to explicit `mpls label` segment lists can use the completed Stage 7.8
pipeline directly. Unsupported forms continue to fail closed rather than block or weaken the
implemented semantics.
