# General Segment Routing Architecture / 通用 SR 架构

## Scope

SR is not another route-preference plane. Batfish parses vendor syntax into a vendor-independent
SR configuration; Minesweeper consumes the stable guarded underlay and resolves SID and policy
state. Traffic execution consumes the resolved SR state later.

```text
vendor parser -> vendor-specific AST -> Batfish SR model
                                         +
                              guarded IGP/MAIN state
                                         |
                                         v
                          Minesweeper symbolicsr layer
                      guarded SID DB and policy resolution
                                         |
                                         v
                         symbolic traffic/TE (later stage)
```

The core model and symbolic algorithm must not depend on router names, the demo topology, Cisco
syntax, or IS-IS. Cisco IOS/XR are parser adapters; IS-IS is the first underlay provider. OSPF and
other vendors must be able to implement the same typed boundaries.

## Repository audit

The current Batfish revision has no structured Java model or grammar production for Prefix-SID,
Node-SID, Adjacency-SID, SRGB/SRLB, segment lists, binding SID, SR policy, candidate paths, or SR
steering. Generic MPLS constants and Juniper MPLS RIB names are insufficient for SR semantics.

The commands in `networks/traffic_demo` are therefore not available in normalized
`Configuration`; accepting or ignoring their text is not equivalent to parsing them. Minesweeper
must not read the raw configuration to compensate for this gap.

## Vendor-independent ownership

`Configuration` owns an optional device-wide `SegmentRoutingConfig`:

- enabled data planes (`MPLS`, `SRV6`);
- device label/locator allocation blocks such as SRGB and SRLB;
- a map from VRF name to `SegmentRoutingVrfConfig`.

Each VRF configuration owns typed collections of:

- Prefix/Node SIDs, with IPv4/IPv6 prefix, SID value/index, algorithm and flags;
- adjacency SIDs, identified by interface/neighbor rather than display text;
- ordered segment lists;
- SR policies and candidate paths;
- steering entries.

Policy identity is `(node, VRF, color, typed IPv4/IPv6 endpoint)`. Candidate identity is a stable
configured name within that policy; preference and weight are payload used for selection, not
identity. Segment-list identity is `(node, VRF, name)`, and segment order is an explicit unsigned
sequence value rather than Java list position. A segment either references a typed SID binding or
contains an explicit absolute MPLS/SRv6 SID. An unscoped raw `MPLS_INDEX` is rejected because no
SRGB/SRLB namespace can be selected correctly from that value alone.

SID values are a tagged union. MPLS labels and indexes are bounded integers; SRv6 SIDs are IPv6
values. A numeric index is not silently converted to an absolute label until an allocation block
is selected and validated.

Policy endpoints and prefix identities are also typed IPv4/IPv6 unions. Names are configuration
references, not semantic SID or advertisement identities.

## Minesweeper boundary

The `symbolicsr` layer consumes a protocol-independent interface:

```java
interface SymbolicUnderlayReachability {
  Optional<RouteGuard> prefixReachability(String node, String vrf, SrPrefix prefix, int algorithm);
  ImmutableList<SymbolicNextHopBranch> prefixNextHops(
      String node, String vrf, SrPrefix prefix, int algorithm);
  Optional<SymbolicAdjacencyAvailability> adjacencyAvailability(
      String node, String vrf, String interfaceName);
}
```

An empty prefix result means that the converged underlay contains no satisfiable exact
advertisement for that SR prefix. Prefix-SID discovery is exact-prefix based: a covering default
route does not manufacture an IGP Prefix-SID advertisement. Forwarding LPM is a later operation.

The initial IS-IS provider reads guarded L1/L2 and MAIN state plus canonical `LinkFailureKey`.
Future OSPF support implements the same interface; no `IsisRoute` appears in the general SID or
policy model.

Guard ownership is:

| Object | Guard source |
| --- | --- |
| Prefix/Node SID | configuration guard AND underlay prefix reachability |
| Adjacency SID | configuration guard AND canonical adjacency/link availability |
| Segment resolution | SID availability AND reachability to the segment owner/endpoint |
| Segment list | ordered conjunction of segment resolution guards |
| Candidate path | configuration guard AND referenced segment-list guard |
| SR policy | selection over candidate preference, with ECMP/weight retained as data |

Each Stage 7.7 policy database evaluates all candidates against one stable SID/underlay snapshot.
The reconciler is not fixed to that snapshot: with fixed SR configuration it compares policy state
again at every subsequent stable underlay boundary and emits the semantic difference.
For candidate `c`, `availability(c)` is the disjunction of its satisfiable numeric forwarding
branches. Its selection condition is:

```text
selection(c) = availability(c) AND NOT(OR availability(higher-preference candidates))
```

Candidates in the same preference group do not suppress one another; their configured weights are
retained but are not interpreted as traffic load at this layer. Each selected branch keeps typed
SID and canonical link dependencies. A stable candidate key excludes preference, weight, guards,
and report text. A concrete payload change under that key is `REPLACED`; logical guard change is
`GUARD_CHANGED`. When forwarding identity itself changes, the old key is `REMOVED` and the new key
is `ADDED` in the same atomic delta batch. Update-list order has no execution meaning, and consumers
must not pair unrelated removals and additions. A missing dependency recursively removes the
candidate and its child forwarding contributions.

Policy reconciliation runs after every stable underlay boundary, not only after a nonempty SID
delta. This distinction is required because ECMP/next-hop branches can change while their aggregate
prefix availability formula remains logically equivalent. SR configuration is fixed for the
lifetime of this reconciler; configuration changes require a newly constructed pipeline.

Typed Prefix-SID, Node-SID, and Adjacency-SID bindings are supported. A Binding-SID segment that
recursively expands another policy or segment list is not yet supported and fails closed.

An MPLS index remains unresolved in the SID database. A global Prefix/Node-SID index is resolved
against the SRGB of the concrete forwarding next hop; symbolic ECMP/failure branches may therefore
produce different wire labels for the same index. Resolving it once against the source, ingress, or
SID owner and storing that label globally is incorrect. A locally configured Adjacency-SID index is
a different namespace and resolves only against the advertising node's SRLB. The two resolver APIs
are deliberately separate.

Before a concrete next-hop branch is selected, the MPLS output is a typed label plan rather than a
fully numeric stack. Absolute labels and owner-local SRLB values are resolved; Prefix/Node indexes
remain `NEXT_HOP_SRGB` instructions. Symbolic forwarding later partitions the plan by guarded next
hop and resolves each instruction against that neighbor's parsed SRGB.

The IS-IS provider derives each next-hop identity from the selected Batfish `IsisRoute` next-hop IP
and the matching parser-derived directed edge. The branch retains the RIB selection guard and the
same canonical `LinkFailureKey` used by adjacency availability. Adjacency execution direction
(sender to receiver) and route lookup direction (receiver identifies sender) are deliberately
separate typed mappings.

Adjacency availability carries both the symbolic up-guard and the parser-derived canonical
`LinkFailureKey`, plus the directed neighbor endpoint. The Adj-SID database entry depends only on
that directed interface's physical adjacency. Ordered segment resolution tracks the current node:
a local Adj-SID is executable only at its owner, so a remote sequence normally reaches that owner
with a preceding Prefix/Node SID before applying the adjacency instruction. This avoids incorrectly
baking an arbitrary source-to-owner path into the SID binding itself.

The SID database maintains typed contribution and dependency identities. Route text, `toString()`,
list position, or generated report strings are never identities. Withdrawal of an underlay prefix
or adjacency recursively removes dependent SID and policy contributions.

The initial SID lifecycle is synchronized at the underlay engines' stable-state boundary. A
reconciliation compares stable keys and emits `ADDED`, `REMOVED`, `GUARD_CHANGED`, or `REPLACED`:
guard-only changes retain identity, while a changed SID/flags payload under the same binding key is
a replacement. No-op stable callbacks do not manufacture deltas.

## Minimal implementation sequence

1. Add immutable, JSON-serializable Batfish SR value objects and attach the optional root config to
   `Configuration`; test validation, equality, serialization, IPv4/IPv6, label/index distinction,
   multi-VRF isolation, and reference identity.
2. Add vendor-specific representation and conversion before grammar listeners write normalized
   objects. Implement Cisco IOS and XR adapters without embedding vendor syntax in the common model.
3. Parse general SR constructs; use `traffic_demo` only as one integration fixture alongside
   multiple VRFs, arbitrary names, label/index modes, multiple candidate paths, and invalid input.
4. Add the protocol-independent Minesweeper underlay interface and IS-IS implementation.
5. Add guarded SID database lifecycle, then segment-list and SR-policy resolution.
6. Add deterministic readable/JSON output. Traffic/load execution remains a separate stage.

Stage 7.8 completes item 6. `BatfishSymbolicRoutePipeline` constructs the guarded SID and SR-policy
reconcilers from the same parsed configurations and converged symbolic IS-IS networks. Its result
exposes the typed database plus deterministic candidate/forwarding records. Default text and JSON
use display-simplified guards; raw variants retain the exact formulas stored by the database.
Report records are views only and never participate in candidate, contribution, or dependency
identity.

Unsupported syntax or semantic combinations must produce an explicit warning or fail closed; they
must never yield a partially populated SR object that appears successful.
