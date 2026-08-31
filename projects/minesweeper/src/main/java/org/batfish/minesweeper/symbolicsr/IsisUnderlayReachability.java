package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.route.nh.NextHop;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.minesweeper.symbolicroute.BatfishIsisEdge;
import org.batfish.minesweeper.symbolicroute.GuardedRib;
import org.batfish.minesweeper.symbolicroute.GuardedRibEntry;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteNetwork;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteSession;

/** IS-IS L1/L2 implementation of exact guarded prefix reachability. */
public final class IsisUnderlayReachability implements SymbolicUnderlayReachability {
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l1;
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l2;
  private final Map<AdjacencyEndpoint, SymbolicAdjacencyAvailability> _adjacencies;
  private final Map<NextHopLookup, NextHopTarget> _nextHopTargets;

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
    _nextHopTargets = new LinkedHashMap<>();
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
                      session.getLinkFailureKey(),
                      session.getLinkGuard(),
                      new SymbolicAdjacencyEndpoint(
                          edge.getReceiverConfiguration().getHostname(),
                          edge.getReceiverInterface().getVrfName(),
                          edge.getReceiverInterface().getName()));
              SymbolicAdjacencyAvailability old = _adjacencies.put(endpoint, availability);
              if (old != null
                  && (!old.getFailureKey().equals(availability.getFailureKey())
                      || !old.getGuard().isEquivalentTo(availability.getGuard())
                      || !old.getTarget().equals(availability.getTarget()))) {
                throw new IllegalArgumentException("conflicting canonical adjacency dependency");
              }
              ConcreteInterfaceAddress senderAddress =
                  edge.getSenderInterface().getConcreteAddress();
              if (senderAddress == null) {
                throw new IllegalArgumentException(
                    "numbered IS-IS point-to-point interface is required");
              }
              NextHopLookup lookup =
                  new NextHopLookup(
                      edge.getReceiverConfiguration().getHostname(),
                      edge.getReceiverInterface().getVrfName(),
                      senderAddress.getIp());
              NextHopTarget target =
                  new NextHopTarget(
                      new SymbolicAdjacencyEndpoint(
                          edge.getSenderConfiguration().getHostname(),
                          edge.getSenderInterface().getVrfName(),
                          edge.getSenderInterface().getName()),
                      availability.getFailureKey());
              NextHopTarget oldTarget = _nextHopTargets.put(lookup, target);
              if (oldTarget != null && !oldTarget.equals(target)) {
                throw new IllegalArgumentException("conflicting IS-IS next-hop identity");
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
  public ImmutableList<SymbolicNextHopBranch> prefixNextHops(
      String node, String vrf, SrPrefix prefix, int algorithm) {
    requireNonNull(node, "node must be provided");
    requireNonNull(vrf, "VRF must be provided");
    requireNonNull(prefix, "prefix must be provided");
    if (prefix.getFamily() != SrPrefix.Family.IPV4 || algorithm != 0) {
      return ImmutableList.of();
    }
    Map<NextHopTarget, RouteGuard> branches = new LinkedHashMap<>();
    collectNextHops(branches, _l1.getRib(node), node, vrf, prefix);
    collectNextHops(branches, _l2.getRib(node), node, vrf, prefix);
    return branches.entrySet().stream()
        .map(
            entry ->
                new SymbolicNextHopBranch(
                    entry.getKey()._endpoint,
                    entry.getKey()._linkFailureKey,
                    entry.getValue().simplify()))
        .sorted(
            Comparator.comparing((SymbolicNextHopBranch branch) -> branch.getNextHop().getNode())
                .thenComparing(branch -> branch.getNextHop().getVrf())
                .thenComparing(branch -> branch.getNextHop().getInterfaceName()))
        .collect(ImmutableList.toImmutableList());
  }

  private void collectNextHops(
      Map<NextHopTarget, RouteGuard> branches,
      GuardedRib<AnnotatedRoute<IsisRoute>> rib,
      String node,
      String vrf,
      SrPrefix prefix) {
    for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry : rib.getEntries()) {
      if (!entry.getSymbolicRoute().getKey().getVrf().equals(vrf)
          || !entry.getSymbolicRoute().getKey().getNetwork().equals(prefix.getIpv4())
          || !entry.getSelectionGuard().isSatisfiable()) {
        continue;
      }
      NextHop nextHop = entry.getSymbolicRoute().getRoute().getRoute().getNextHop();
      if (!(nextHop instanceof NextHopIp)) {
        continue;
      }
      NextHopTarget target =
          _nextHopTargets.get(new NextHopLookup(node, vrf, ((NextHopIp) nextHop).getIp()));
      if (target == null) {
        continue;
      }
      RouteGuard old = branches.get(target);
      branches.put(
          target,
          old == null ? entry.getSelectionGuard() : old.or(entry.getSelectionGuard()).simplify());
    }
  }

  private static final class NextHopLookup {
    private final String _node;
    private final String _vrf;
    private final Ip _ip;

    private NextHopLookup(String node, String vrf, Ip ip) {
      _node = requireNonNull(node);
      _vrf = requireNonNull(vrf);
      _ip = requireNonNull(ip);
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof NextHopLookup)) {
        return false;
      }
      NextHopLookup that = (NextHopLookup) object;
      return _node.equals(that._node) && _vrf.equals(that._vrf) && _ip.equals(that._ip);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_node, _vrf, _ip);
    }
  }

  private static final class NextHopTarget {
    private final SymbolicAdjacencyEndpoint _endpoint;
    private final LinkFailureKey _linkFailureKey;

    private NextHopTarget(SymbolicAdjacencyEndpoint endpoint, LinkFailureKey linkFailureKey) {
      _endpoint = requireNonNull(endpoint);
      _linkFailureKey = requireNonNull(linkFailureKey);
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof NextHopTarget)) {
        return false;
      }
      NextHopTarget that = (NextHopTarget) object;
      return _endpoint.equals(that._endpoint) && _linkFailureKey.equals(that._linkFailureKey);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_endpoint, _linkFailureKey);
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
