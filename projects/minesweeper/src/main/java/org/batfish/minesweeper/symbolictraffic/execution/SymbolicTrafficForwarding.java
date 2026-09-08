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
      return forwardIp(router, flow, incomingFraction);
    }
    return forwardSr(router, flow, stack, incomingFraction);
  }

  SymbolicTrafficMatrix forwardIp(
      String router, TrafficFlow flow, SymbolicTrafficFraction incomingFraction) {
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
        matrix.add(resolveNhIp(router, flow, rule.getIndirectNextHop(), share));
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
        Ip firstIp = _routerAddresses.get(path.getFirstNode());
        if (firstIp == null) {
          continue;
        }
        TrafficLabelStack stack = path.toStack();
        for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> entry :
            RouteIterationEncoding.vsr(path, policy.getPaths(), igp, firstIp).entrySet()) {
          TrafficGraphEdge link = entry.getKey();
          matrix.put(
              link,
              stack,
              matrix.get(link, stack).plus(incomingFraction.times(entry.getValue())));
        }
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
