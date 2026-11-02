# Shared protocol selection

The SMT reachability driver passes `SmtProtocolSelection.fromRuntime()` to
`BatfishParsedSnapshotPipelineInputBuilder.buildSelected`. Set `SMT_PROTOCOLS=bgp`
(or system property `batfish.smt.protocols=bgp`, which takes precedence) for a
BGP-only run. Selection occurs before symbolic convergence and MAIN selection;
filtering final JSON candidates is not equivalent.

Connected/local/configured static origins remain available. BGP-only input has
no IS-IS L1/L2 edges, sessions or seeds, so IS-IS cannot supply redistribution
sources or symbolic recursive resolution. The BGP preference oracle receives
only connected/local/static concrete routes, rather than a mixed-protocol
converged RIB whose BGP winners may themselves depend on IS-IS. This is intended
for the builder's supported numbered, directly connected eBGP scope; it does not
claim support for arbitrary multihop/iBGP recursive resolution.

When BGP is disabled its edges, sessions and redistribution rules are absent.
Existing explicit `build` callers retain BGP+IS-IS behavior. OSPF is not supported
by this symbolic pipeline: `buildSelected` rejects it rather than silently
exporting a narrower model. In particular an unset runtime selection defaults
to all SMT families and is rejected here; set the supported scope explicitly.

SR Policy configuration/export is separate from dynamic protocol selection;
this change does not add or change an SR forwarding enable switch. Generate a
new output directory and rerun slicing/consistency rather than combining newly
generated JSON with archived SMT or seeds.
