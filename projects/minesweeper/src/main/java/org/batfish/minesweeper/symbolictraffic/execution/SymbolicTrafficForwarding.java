package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nullable;
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
 * multiplies {@code VIGP}. Adj-SID forwarding pops the Adj-SID, keeps the remaining typed stack,
 * and requires {@code source = router}. After the SR stack is consumed, IP lookup re-enters the
 * normal policy-aware path; the just-consumed policy is suppressed only for that local re-entry.
 */
class SymbolicTrafficForwarding {

  private final TrafficGraph _graph;

  /** Guarded main RIB used for destination-prefix forwarding. */
  private final Map<String, List<ForwardingRule>> _mainRibs;

  /** Guarded underlay/IGP RIB used only by YU's {@code VIGP}. */
  private final Map<String, List<ForwardingRule>> _igpRibs;

  private final Map<String, List<SrPolicy>> _srPolicies;

  private final Map<String, Ip> _routerAddresses;

  SymbolicTrafficForwarding(TrafficGraph graph) {
    this(
        graph,
        Collections.<String, List<ForwardingRule>>emptyMap(),
        Collections.<String, List<ForwardingRule>>emptyMap(),
        Collections.<String, List<SrPolicy>>emptyMap(),
        Collections.<String, Ip>emptyMap());
  }

  SymbolicTrafficForwarding(
      TrafficGraph graph,
      Map<String, List<ForwardingRule>> ribs,
      Map<String, List<SrPolicy>> srPolicies,
      Map<String, Ip> routerAddresses) {
    this(graph, ribs, ribs, srPolicies, routerAddresses);
  }

  /**
   * Creates YU forwarding with distinct main and underlay guarded RIBs.
   *
   * <p>The main RIB selects a destination route; recursive BGP next-hop and Node-SID resolution
   * must use the underlay RIB only.
   */
  SymbolicTrafficForwarding(
      TrafficGraph graph,
      Map<String, List<ForwardingRule>> mainRibs,
      Map<String, List<ForwardingRule>> igpRibs,
      Map<String, List<SrPolicy>> srPolicies,
      Map<String, Ip> routerAddresses) {
    _graph = graph;
    _mainRibs = copyLists(mainRibs);
    _igpRibs = copyLists(igpRibs);
    _srPolicies = copyLists(srPolicies);
    _routerAddresses = new HashMap<>(routerAddresses);
  }

  TrafficGraph getGraph() {
    return _graph;
  }

  Map<String, List<SrPolicy>> getSrPolicies() {
    return _srPolicies;
  }

  SymbolicTrafficMatrix forward(
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction) {
    if (stack.isEmpty()) {
      return forwardIp(router, flow, incomingFraction, null);
    }
    return forwardSr(router, flow, stack, incomingFraction);
  }

  SymbolicTrafficMatrix forwardIp(
      String router, TrafficFlow flow, SymbolicTrafficFraction incomingFraction) {
    return forwardIp(router, flow, incomingFraction, null);
  }

  private SymbolicTrafficMatrix forwardIp(
      String router,
      TrafficFlow flow,
      SymbolicTrafficFraction incomingFraction,
      @Nullable SrPolicy suppressedPolicy) {
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    List<ForwardingRule> rib = mainRib(router);
    Ip dstIp = flow.getDestination().getStartIp();
    for (ForwardingRule rule : rib) {
      if (!rule.matches(dstIp)) {
        continue;
      }
      SymbolicTrafficFraction share =
          incomingFraction.times(RouteSelectionEncoding.ecmpRatio(rule, rib, dstIp));
      if (rule.isTerminal() || share.isZero()) {
        continue;
      }
      if (rule.isIndirect()) {
        matrix.add(resolveNhIp(router, flow, rule.getIndirectNextHop(), share, suppressedPolicy));
      } else {
        putOnLink(matrix, rule.getDirectNextHop(), TrafficLabelStack.empty(), share);
      }
    }
    return matrix;
  }

  SymbolicTrafficMatrix resolveNhIp(
      String router, TrafficFlow flow, Ip nextHopIp, SymbolicTrafficFraction incomingFraction) {
    return resolveNhIp(router, flow, nextHopIp, incomingFraction, null);
  }

  private SymbolicTrafficMatrix resolveNhIp(
      String router,
      TrafficFlow flow,
      Ip nextHopIp,
      SymbolicTrafficFraction incomingFraction,
      @Nullable SrPolicy suppressedPolicy) {
    SrPolicy policy = matchingSrPolicy(router, flow, nextHopIp);
    if (policy != null && policy != suppressedPolicy) {
      SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
      List<ForwardingRule> igp = igpRib(router);
      for (SrPolicy.Path path : policy.getPaths()) {
        SymbolicTrafficFraction share =
            incomingFraction.times(RouteIterationEncoding.pathShare(path, policy.getPaths()));
        matrix.add(resolveSrPath(router, flow, policy, path, igp, share));
      }
      return matrix;
    }
    return resolveNhIpWithoutSr(router, nextHopIp, incomingFraction);
  }

  /** Indirect next hop resolved with IGP only; used after SR SIDs have been consumed. */
  private SymbolicTrafficMatrix resolveNhIpWithoutSr(
      String router, Ip nextHopIp, SymbolicTrafficFraction incomingFraction) {
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(igpRib(router), nextHopIp).entrySet()) {
      putOnLink(
          matrix,
          entry.getKey(),
          TrafficLabelStack.empty(),
          incomingFraction.times(entry.getValue()));
    }
    return matrix;
  }

  /**
   * {@code g_p} contributes only {@code c_p}. Node-SID first hops go through {@code VIGP}. Adj-SID
   * first hops pop and require {@code source = router}. A Node-SID equal to the current router pops
   * instead of looking up IGP to self. As in YU Algorithm 2, an empty remainder re-enters normal
   * {@code forwardIp} processing and can match a policy at that router. The just-consumed policy is
   * suppressed for that one re-entry, preventing a zero-length SR policy from recursively applying
   * itself before Algorithm 1 can advance a hop.
   */
  private SymbolicTrafficMatrix resolveSrPath(
      String router,
      TrafficFlow flow,
      SrPolicy activePolicy,
      SrPolicy.Path path,
      List<ForwardingRule> igp,
      SymbolicTrafficFraction share) {
    return forwardSr(router, flow, path.toStack(), share, igp, activePolicy);
  }

  SymbolicTrafficMatrix forwardSr(
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction) {
    return forwardSr(router, flow, stack, incomingFraction, igpRib(router), null);
  }

  private SymbolicTrafficMatrix forwardSr(
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction,
      List<ForwardingRule> igp,
      @Nullable SrPolicy activePolicy) {
    SrPolicy.Segment first = stack.getFirst();
    if (first.isAdjacency()) {
      return forwardAdjacency(router, first, stack.pop(), incomingFraction);
    }
    if (router.equals(first.getRouter())) {
      TrafficLabelStack rest = stack.pop();
      if (rest.isEmpty()) {
        return forwardIp(router, flow, incomingFraction, activePolicy);
      }
      return forwardSr(router, flow, rest, incomingFraction, igp, activePolicy);
    }
    Ip firstIp = _routerAddresses.get(first.getRouter());
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    if (firstIp == null) {
      return matrix;
    }
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
        RouteIterationEncoding.vigp(igp, firstIp).entrySet()) {
      putOnLink(matrix, entry.getKey(), stack, incomingFraction.times(entry.getValue()));
    }
    return matrix;
  }

  /**
   * Execute a local Adj-SID: pop it, place {@code ω} on the adjacency, keep the remaining typed
   * stack. Source must equal the current router.
   */
  private SymbolicTrafficMatrix forwardAdjacency(
      String router,
      SrPolicy.Segment adjacency,
      TrafficLabelStack rest,
      SymbolicTrafficFraction incomingFraction) {
    SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
    if (!router.equals(adjacency.getRouter())) {
      return matrix;
    }
    TrafficGraphEdge link = outgoingTo(router, adjacency.getPeer());
    if (link == null) {
      return matrix;
    }
    putOnLink(matrix, link, rest, adjacencyShare(adjacency, incomingFraction));
    return matrix;
  }

  private SymbolicTrafficFraction adjacencyShare(
      SrPolicy.Segment adjacency,
      SymbolicTrafficFraction share) {
    SymbolicTrafficFraction out = share;
    if (adjacency.getAvailability() != null) {
      out = out.times(SymbolicTrafficFraction.fromGuard(adjacency.getAvailability()));
    }
    return out;
  }

  private void putOnLink(
      SymbolicTrafficMatrix matrix,
      TrafficGraphEdge link,
      TrafficLabelStack stack,
      SymbolicTrafficFraction share) {
    if (link == null || share.isZero()) {
      return;
    }
    matrix.put(link, stack, matrix.get(link, stack).plus(share));
  }

  private TrafficGraphEdge outgoingTo(String router, String peer) {
    for (TrafficGraphEdge edge : _graph.getOutgoingEdges(router)) {
      if (peer.equals(edge.getPeer())) {
        return edge;
      }
    }
    return null;
  }

  private List<ForwardingRule> mainRib(String router) {
    List<ForwardingRule> rules = _mainRibs.get(router);
    if (rules == null) {
      return Collections.emptyList();
    }
    return rules;
  }

  private List<ForwardingRule> igpRib(String router) {
    List<ForwardingRule> rules = _igpRibs.get(router);
    if (rules == null) {
      return Collections.emptyList();
    }
    return rules;
  }

  /**
   * Unique most-specific matching policy. Color and name are required when the policy sets them. A
   * tie at the same specificity is an error.
   */
  private SrPolicy matchingSrPolicy(String router, TrafficFlow flow, Ip nextHopIp) {
    List<SrPolicy> policies = _srPolicies.get(router);
    if (policies == null) {
      return null;
    }
    SrPolicy best = null;
    int bestSpecificity = -1;
    for (SrPolicy policy : policies) {
      if (!policy.matches(router, flow, nextHopIp)) {
        continue;
      }
      int specificity = policy.matchSpecificity();
      if (best != null && specificity == bestSpecificity) {
        throw new IllegalArgumentException(
            "ambiguous SR policies at " + router + " for " + flow.getId());
      }
      if (specificity > bestSpecificity) {
        best = policy;
        bestSpecificity = specificity;
      }
    }
    return best;
  }

  private static <T> Map<String, List<T>> copyLists(Map<String, List<T>> values) {
    Map<String, List<T>> copied = new HashMap<>();
    for (Map.Entry<String, List<T>> entry : values.entrySet()) {
      copied.put(entry.getKey(), Collections.unmodifiableList(new ArrayList<>(entry.getValue())));
    }
    return copied;
  }
}
