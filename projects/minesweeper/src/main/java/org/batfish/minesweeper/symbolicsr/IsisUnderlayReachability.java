package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.minesweeper.symbolicroute.BatfishIsisEdge;
import org.batfish.minesweeper.symbolicroute.GuardedRib;
import org.batfish.minesweeper.symbolicroute.GuardedRibEntry;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteNetwork;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteSession;

/** IS-IS L1/L2 implementation of exact guarded prefix reachability. */
public final class IsisUnderlayReachability implements SymbolicUnderlayReachability {
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l1;
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l2;
  private final Map<AdjacencyEndpoint, SymbolicAdjacencyAvailability> _adjacencies;

  public IsisUnderlayReachability(
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l1,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l2,
      Iterable<BatfishIsisEdge> edges,
      Iterable<SymbolicRouteSession> sessions) {
    _l1 = requireNonNull(l1, "L1 network must be provided");
    _l2 = requireNonNull(l2, "L2 network must be provided");
    Map<String, SymbolicRouteSession> sessionsById = new LinkedHashMap<>();
    requireNonNull(sessions, "sessions must be provided")
        .forEach(
            session -> {
              SymbolicRouteSession old = sessionsById.put(session.getSessionId(), session);
              if (old != null
                  && (!old.getSender().equals(session.getSender())
                      || !old.getReceiver().equals(session.getReceiver())
                      || !Objects.equals(old.getLinkFailureKey(), session.getLinkFailureKey())
                      || !old.getLinkGuard().isEquivalentTo(session.getLinkGuard()))) {
                throw new IllegalArgumentException("conflicting symbolic session identity");
              }
            });
    _adjacencies = new LinkedHashMap<>();
    requireNonNull(edges, "edges must be provided")
        .forEach(
            edge -> {
              SymbolicRouteSession session = sessionsById.get(edge.getSessionId());
              if (session == null || session.getLinkFailureKey() == null) {
                return;
              }
              AdjacencyEndpoint endpoint =
                  new AdjacencyEndpoint(
                      edge.getSenderConfiguration().getHostname(),
                      edge.getSenderInterface().getVrfName(),
                      edge.getSenderInterface().getName());
              SymbolicAdjacencyAvailability availability =
                  new SymbolicAdjacencyAvailability(
                      session.getLinkFailureKey(), session.getLinkGuard());
              SymbolicAdjacencyAvailability old = _adjacencies.put(endpoint, availability);
              if (old != null
                  && (!old.getFailureKey().equals(availability.getFailureKey())
                      || !old.getGuard().isEquivalentTo(availability.getGuard()))) {
                throw new IllegalArgumentException("conflicting canonical adjacency dependency");
              }
            });
  }

  @Override
  public Optional<SymbolicAdjacencyAvailability> adjacencyAvailability(
      String node, String vrf, String interfaceName) {
    return Optional.ofNullable(_adjacencies.get(new AdjacencyEndpoint(node, vrf, interfaceName)));
  }

  private static final class AdjacencyEndpoint {
    private final String _node;
    private final String _vrf;
    private final String _interfaceName;

    private AdjacencyEndpoint(String node, String vrf, String interfaceName) {
      _node = requireNonNull(node, "node must be provided");
      _vrf = requireNonNull(vrf, "VRF must be provided");
      _interfaceName = requireNonNull(interfaceName, "interface must be provided");
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof AdjacencyEndpoint)) {
        return false;
      }
      AdjacencyEndpoint that = (AdjacencyEndpoint) object;
      return _node.equals(that._node)
          && _vrf.equals(that._vrf)
          && _interfaceName.equals(that._interfaceName);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_node, _vrf, _interfaceName);
    }
  }

  @Override
  public Optional<RouteGuard> prefixReachability(
      String node, String vrf, SrPrefix prefix, int algorithm) {
    requireNonNull(node, "node must be provided");
    requireNonNull(vrf, "VRF must be provided");
    requireNonNull(prefix, "prefix must be provided");
    if (prefix.getFamily() != SrPrefix.Family.IPV4 || algorithm != 0) {
      return Optional.empty();
    }
    RouteGuard combined = null;
    combined = combine(combined, _l1.getRib(node), vrf, prefix);
    combined = combine(combined, _l2.getRib(node), vrf, prefix);
    return Optional.ofNullable(combined == null ? null : combined.simplify());
  }

  private static RouteGuard combine(
      RouteGuard accumulated,
      GuardedRib<AnnotatedRoute<IsisRoute>> rib,
      String vrf,
      SrPrefix prefix) {
    RouteGuard result = accumulated;
    for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry : rib.getEntries()) {
      if (!entry.getSymbolicRoute().getKey().getVrf().equals(vrf)
          || !entry.getSymbolicRoute().getKey().getNetwork().equals(prefix.getIpv4())
          || !entry.getSelectionGuard().isSatisfiable()) {
        continue;
      }
      result =
          result == null
              ? entry.getSelectionGuard()
              : result.or(entry.getSelectionGuard()).simplify();
    }
    return result;
  }
}
