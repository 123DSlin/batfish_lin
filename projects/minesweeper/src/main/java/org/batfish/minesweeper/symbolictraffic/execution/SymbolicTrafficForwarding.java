package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.batfish.datamodel.Ip;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * YU Algorithm 2 {@code forward(R, f, S, ω)}.
 *
 * <p>Empty stack uses {@code forwardIp}; otherwise {@code forwardSr}. Encodings of {@code s_r},
 * {@code c_r}, {@code VIGP}, and {@code VSR} are computed by {@link RouteSelectionEncoding} and
 * {@link RouteIterationEncoding}.
 *
 * <p>Policy-path guard {@code g_p} is only the numerator of {@code c_p}. Node-SID forwarding still
 * multiplies {@code VIGP} (IGP availability). Adj-SID forwarding uses the adjacency and requires
 * its source to be the current router.
 */
class SymbolicTrafficForwarding {

  private final TrafficGraph _graph;

  private final Map<String, List<ForwardingRule>> _ribs;

  private final Map<String, List<SrPolicy>> _srPolicies;

  private final Map<String, Ip> _routerAddresses;

  SymbolicTrafficForwarding(TrafficGraph graph) {
    this(
        graph,
        Collections.<String, List<ForwardingRule>>emptyMap(),
        Collections.<String, List<SrPolicy>>emptyMap(),
        Collections.<String, Ip>emptyMap());
  }

  SymbolicTrafficForwarding(
      TrafficGraph graph,
      Map<String, List<ForwardingRule>> ribs,
      Map<String, List<SrPolicy>> srPolicies,
      Map<String, Ip> routerAddresses) {
    _graph = graph;
    _ribs = new HashMap<>(ribs);
    _srPolicies = new HashMap<>(srPolicies);
    _routerAddresses = new HashMap<>(routerAddresses);
  }

  TrafficGraph getGraph() {
    return _graph;
  }

  SymbolicTrafficMatrix forward(
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction) {
    if (stack.isEmpty()) {
      return forwardIp(router, flow, incomingFraction, true);
    }
    return forwardSr(router, flow, stack, incomingFraction);
  }

  SymbolicTrafficMatrix forwardIp(
      String router, TrafficFlow flow, SymbolicTrafficFraction incomingFraction) {
    return forwardIp(router, flow, incomingFraction, true);
  }

  private SymbolicTrafficMatrix forwardIp(
      String router,
      TrafficFlow flow,
      SymbolicTrafficFraction incomingFraction,
      boolean applySrPolicy) {
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    List<ForwardingRule> rib = rib(router);
    Ip dstIp = flow.getDestination().getStartIp();
    for (ForwardingRule rule : rib) {
      if (!rule.matches(dstIp)) {
        continue;
      }
      SymbolicTrafficFraction share =
          incomingFraction.times(RouteSelectionEncoding.ecmpRatio(rule, rib, dstIp));
      if (rule.isIndirect()) {
        if (applySrPolicy) {
          matrix.add(resolveNhIp(router, flow, rule.getIndirectNextHop(), share));
        } else {
          matrix.add(resolveNhIpWithoutSr(router, flow, rule.getIndirectNextHop(), share));
        }
      } else {
        TrafficGraphEdge link = rule.getDirectNextHop();
        matrix.put(
            link,
            TrafficLabelStack.empty(),
            matrix.get(link, TrafficLabelStack.empty()).plus(share));
      }
    }
    return matrix;
  }

  SymbolicTrafficMatrix resolveNhIp(
      String router, TrafficFlow flow, Ip nextHopIp, SymbolicTrafficFraction incomingFraction) {
    SrPolicy policy = matchingSrPolicy(router, flow, nextHopIp);
    if (policy != null) {
      SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
      List<ForwardingRule> igp = rib(router);
      for (SrPolicy.Path path : policy.getPaths()) {
        SymbolicTrafficFraction share =
            incomingFraction.times(RouteIterationEncoding.pathShare(path, policy.getPaths()));
        matrix.add(resolveSrPath(router, flow, path, igp, share));
      }
      return matrix;
    }
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(rib(router), nextHopIp).entrySet()) {
      TrafficGraphEdge link = entry.getKey();
      matrix.put(
          link,
          TrafficLabelStack.empty(),
          matrix
              .get(link, TrafficLabelStack.empty())
              .plus(incomingFraction.times(entry.getValue())));
    }
    return matrix;
  }

  /** Indirect next hop resolved with IGP only; used after a headend SID has already been popped. */
  private SymbolicTrafficMatrix resolveNhIpWithoutSr(
      String router, TrafficFlow flow, Ip nextHopIp, SymbolicTrafficFraction incomingFraction) {
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(rib(router), nextHopIp).entrySet()) {
      TrafficGraphEdge link = entry.getKey();
      matrix.put(
          link,
          TrafficLabelStack.empty(),
          matrix
              .get(link, TrafficLabelStack.empty())
              .plus(incomingFraction.times(entry.getValue())));
    }
    return matrix;
  }

  /**
   * {@code g_p} contributes only {@code c_p}. Node-SID first hops go through {@code VIGP}. Adj-SID
   * first hops require {@code source = router} and use that adjacency. A Node-SID equal to the
   * current router pops instead of looking up IGP to self.
   */
  private SymbolicTrafficMatrix resolveSrPath(
      String router,
      TrafficFlow flow,
      SrPolicy.Path path,
      List<ForwardingRule> igp,
      SymbolicTrafficFraction share) {
    SrPolicy.Segment first = path.getFirstSegment();
    if (first.isAdjacency()) {
      SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
      if (!router.equals(first.getRouter())) {
        return matrix;
      }
      TrafficGraphEdge link = outgoingTo(router, first.getPeer());
      if (link == null) {
        return matrix;
      }
      matrix.put(link, path.toStack(), share);
      return matrix;
    }
    if (router.equals(first.getRouter())) {
      List<String> rest = new ArrayList<>(path.toStack().getLabels());
      rest.remove(0);
      if (rest.isEmpty()) {
        return forwardIp(router, flow, share, false);
      }
      return forward(router, flow, new TrafficLabelStack(rest), share);
    }
    Ip firstIp = _routerAddresses.get(first.getRouter());
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    if (firstIp == null) {
      return matrix;
    }
    TrafficLabelStack stack = path.toStack();
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(igp, firstIp).entrySet()) {
      TrafficGraphEdge link = entry.getKey();
      matrix.put(
          link, stack, matrix.get(link, stack).plus(share.times(entry.getValue())));
    }
    return matrix;
  }

  SymbolicTrafficMatrix forwardSr(
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction) {
    List<String> labels = stack.getLabels();
    String first = labels.get(0);
    if (router.equals(first)) {
      List<String> rest = new ArrayList<>(labels.subList(1, labels.size()));
      return forward(router, flow, new TrafficLabelStack(rest), incomingFraction);
    }
    Ip firstIp = _routerAddresses.get(first);
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    if (firstIp == null) {
      return matrix;
    }
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(rib(router), firstIp).entrySet()) {
      TrafficGraphEdge link = entry.getKey();
      matrix.put(
          link,
          stack,
          matrix.get(link, stack).plus(incomingFraction.times(entry.getValue())));
    }
    return matrix;
  }

  private TrafficGraphEdge outgoingTo(String router, String peer) {
    for (TrafficGraphEdge edge : _graph.getOutgoingEdges(router)) {
      if (peer.equals(edge.getPeer())) {
        return edge;
      }
    }
    return null;
  }

  private List<ForwardingRule> rib(String router) {
    List<ForwardingRule> rules = _ribs.get(router);
    if (rules == null) {
      return Collections.emptyList();
    }
    return rules;
  }

  private SrPolicy matchingSrPolicy(String router, TrafficFlow flow, Ip nextHopIp) {
    List<SrPolicy> policies = _srPolicies.get(router);
    if (policies == null) {
      return null;
    }
    for (SrPolicy policy : policies) {
      if (policy.matches(router, flow, nextHopIp)) {
        return policy;
      }
    }
    return null;
  }
}
