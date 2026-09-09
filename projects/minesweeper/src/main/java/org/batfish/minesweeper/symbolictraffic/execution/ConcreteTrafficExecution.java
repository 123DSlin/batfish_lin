package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.GenericRib;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.route.nh.NextHop;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.batfish.datamodel.route.nh.NextHopInterface;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrSegment;
import org.batfish.datamodel.sr.SrSegmentList;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Tolerance / original traffic path: hop-by-hop concrete forwarding on one Batfish dataplane, not
 * YU {@code M[l,S]}.
 *
 * <p>IP flows follow MAIN LPM/ECMP. {@code SR_POLICY} flows apply configured candidate weights at
 * the headend, then continue by IGP.
 */
public final class ConcreteTrafficExecution {

  public static final int DEFAULT_MAX_HOPS = SymbolicTrafficExecution.DEFAULT_MAX_ITERATIONS;

  private ConcreteTrafficExecution() {}

  public static Map<TrafficGraphEdge, Double> simulate(
      TrafficGraph graph, DataPlane dataPlane, Map<String, Configuration> configurations) {
    Map<TrafficGraphEdge, Double> loads = new LinkedHashMap<>();
    if (graph.getFlows().isEmpty()) {
      return loads;
    }
    Map<Ip, String> ipOwners = ipOwners(configurations);
    Map<String, Ip> routerAddresses = GuardedTrafficForwarding.routerAddresses(configurations);
    for (TrafficFlow flow : graph.getFlows()) {
      Map<String, Double> remaining = new HashMap<>();
      remaining.put(flow.getSource(), flow.getDemandGbps());
      boolean applySr = flow.getForwarding() == TrafficFlow.ForwardingType.SR_POLICY;
      for (int hop = 0; hop < DEFAULT_MAX_HOPS; hop++) {
        Map<String, Double> next = new HashMap<>();
        boolean progressed = false;
        for (Map.Entry<String, Double> arrival : remaining.entrySet()) {
          if (arrival.getValue() <= 0.0) {
            continue;
          }
          Map<TrafficGraphEdge, Double> placed =
              forward(
                  graph,
                  dataPlane,
                  configurations,
                  ipOwners,
                  routerAddresses,
                  arrival.getKey(),
                  flow,
                  arrival.getValue(),
                  applySr && arrival.getKey().equals(flow.getSource()) && hop == 0);
          if (placed.isEmpty()) {
            continue;
          }
          progressed = true;
          for (Map.Entry<TrafficGraphEdge, Double> placement : placed.entrySet()) {
            TrafficGraphEdge edge = placement.getKey();
            loads.put(edge, loads.getOrDefault(edge, 0.0) + placement.getValue());
            if (edge.getPeer() != null) {
              next.put(edge.getPeer(), next.getOrDefault(edge.getPeer(), 0.0) + placement.getValue());
            }
          }
        }
        if (!progressed) {
          break;
        }
        remaining = next;
      }
    }
    return loads;
  }

  private static Map<TrafficGraphEdge, Double> forward(
      TrafficGraph graph,
      DataPlane dataPlane,
      Map<String, Configuration> configurations,
      Map<Ip, String> ipOwners,
      Map<String, Ip> routerAddresses,
      String router,
      TrafficFlow flow,
      double mass,
      boolean applySr) {
    if (applySr) {
      Map<TrafficGraphEdge, Double> sr = forwardSr(graph, dataPlane, configurations, ipOwners, routerAddresses, router, flow, mass);
      if (!sr.isEmpty()) {
        return sr;
      }
    }
    return forwardIp(graph, dataPlane, ipOwners, router, flow.getDestination().getStartIp(), mass);
  }

  private static Map<TrafficGraphEdge, Double> forwardSr(
      TrafficGraph graph,
      DataPlane dataPlane,
      Map<String, Configuration> configurations,
      Map<Ip, String> ipOwners,
      Map<String, Ip> routerAddresses,
      String router,
      TrafficFlow flow,
      double mass) {
    Configuration configuration = configurations.get(router);
    if (configuration == null || configuration.getSegmentRoutingConfig() == null) {
      return new LinkedHashMap<>();
    }
    org.batfish.datamodel.sr.SrPolicy policy = matchingPolicy(configuration.getSegmentRoutingConfig(), flow);
    if (policy == null) {
      return new LinkedHashMap<>();
    }
    SegmentRoutingVrfConfig vrf =
        configuration.getSegmentRoutingConfig().getVrfs().get(Configuration.DEFAULT_VRF_NAME);
    Map<String, SrSegmentList> lists = new HashMap<>();
    if (vrf != null) {
      for (SrSegmentList list : vrf.getSegmentLists()) {
        lists.put(list.getKey().getName(), list);
      }
    }
    long totalWeight = 0L;
    List<SrCandidatePath> usable = new ArrayList<>();
    for (SrCandidatePath candidate : policy.getCandidates()) {
      if (lists.containsKey(candidate.getSegmentList())) {
        usable.add(candidate);
        totalWeight += candidate.getWeight();
      }
    }
    Map<TrafficGraphEdge, Double> placed = new LinkedHashMap<>();
    if (totalWeight == 0L) {
      return placed;
    }
    for (SrCandidatePath candidate : usable) {
      double share = mass * ((double) candidate.getWeight() / (double) totalWeight);
      SrSegmentList list = lists.get(candidate.getSegmentList());
      TrafficGraphEdge first =
          firstHop(graph, dataPlane, configurations, ipOwners, routerAddresses, router, list);
      if (first != null) {
        placed.put(first, placed.getOrDefault(first, 0.0) + share);
      }
    }
    return placed;
  }

  @Nullable
  private static TrafficGraphEdge firstHop(
      TrafficGraph graph,
      DataPlane dataPlane,
      Map<String, Configuration> configurations,
      Map<Ip, String> ipOwners,
      Map<String, Ip> routerAddresses,
      String router,
      SrSegmentList list) {
    SrSegment first = list.getSegments().get(0);
    SrSidBindingKey binding = first.getBindingKey();
    if (binding != null) {
      if (binding.getType() == SrSidBindingKey.Type.ADJACENCY) {
        return GuardedTrafficForwarding.outgoingByInterface(
            graph, router, binding.getInterfaceName());
      }
      Ip target = routerAddresses.get(binding.getNode());
      if (target == null) {
        return null;
      }
      Map<TrafficGraphEdge, Double> hop = forwardIp(graph, dataPlane, ipOwners, router, target, 1.0);
      if (hop.isEmpty()) {
        return null;
      }
      return hop.keySet().iterator().next();
    }
    if (first.getSid() != null
        && first.getSid().getType() == org.batfish.datamodel.sr.SrSidValue.Type.MPLS_LABEL) {
      return firstHopForLabel(graph, configurations, router, first.getSid().getMplsLabel());
    }
    return null;
  }

  @Nullable
  private static TrafficGraphEdge firstHopForLabel(
      TrafficGraph graph, Map<String, Configuration> configurations, String router, long label) {
    Configuration configuration = configurations.get(router);
    if (configuration == null || configuration.getSegmentRoutingConfig() == null) {
      return null;
    }
    for (SegmentRoutingVrfConfig vrf : configuration.getSegmentRoutingConfig().getVrfs().values()) {
      for (org.batfish.datamodel.sr.SrSidBinding sid : vrf.getSidBindings()) {
        if (sid.getSid().getType() != org.batfish.datamodel.sr.SrSidValue.Type.MPLS_LABEL
            || sid.getSid().getMplsLabel() != label) {
          continue;
        }
        if (sid.getKey().getType() == SrSidBindingKey.Type.ADJACENCY) {
          return GuardedTrafficForwarding.outgoingByInterface(
              graph, router, sid.getKey().getInterfaceName());
        }
      }
    }
    return null;
  }

  @Nullable
  private static org.batfish.datamodel.sr.SrPolicy matchingPolicy(
      SegmentRoutingConfig sr, TrafficFlow flow) {
    for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
      for (org.batfish.datamodel.sr.SrPolicy policy : vrf.getPolicies()) {
        if (flow.getPolicy() != null && !flow.getPolicy().equals(policy.getName())) {
          continue;
        }
        if (flow.getColor() != null && flow.getColor() != policy.getKey().getColor()) {
          continue;
        }
        return policy;
      }
    }
    return null;
  }

  private static Map<TrafficGraphEdge, Double> forwardIp(
      TrafficGraph graph,
      DataPlane dataPlane,
      Map<Ip, String> ipOwners,
      String router,
      Ip dstIp,
      double mass) {
    Map<TrafficGraphEdge, Double> placed = new LinkedHashMap<>();
    GenericRib<AnnotatedRoute<AbstractRoute>> rib =
        dataPlane.getRibs().get(router) == null
            ? null
            : dataPlane.getRibs().get(router).get(Configuration.DEFAULT_VRF_NAME);
    if (rib == null) {
      return placed;
    }
    Set<AnnotatedRoute<AbstractRoute>> matches = rib.longestPrefixMatch(dstIp);
    if (matches == null || matches.isEmpty()) {
      return placed;
    }
    List<TrafficGraphEdge> hops = new ArrayList<>();
    for (AnnotatedRoute<AbstractRoute> match : matches) {
      TrafficGraphEdge edge = edgeForNextHop(graph, ipOwners, router, match.getRoute().getNextHop());
      if (edge != null) {
        hops.add(edge);
      }
    }
    if (hops.isEmpty()) {
      return placed;
    }
    double share = mass / hops.size();
    for (TrafficGraphEdge hop : hops) {
      placed.put(hop, placed.getOrDefault(hop, 0.0) + share);
    }
    return placed;
  }

  @Nullable
  private static TrafficGraphEdge edgeForNextHop(
      TrafficGraph graph, Map<Ip, String> ipOwners, String router, NextHop nextHop) {
    if (nextHop instanceof NextHopDiscard) {
      return null;
    }
    if (nextHop instanceof NextHopInterface) {
      return GuardedTrafficForwarding.outgoingByInterface(
          graph, router, ((NextHopInterface) nextHop).getInterfaceName());
    }
    if (nextHop instanceof NextHopIp) {
      String peer = ipOwners.get(((NextHopIp) nextHop).getIp());
      if (peer == null || peer.equals(router)) {
        return null;
      }
      for (TrafficGraphEdge edge : graph.getOutgoingEdges(router)) {
        if (peer.equals(edge.getPeer())) {
          return edge;
        }
      }
    }
    return null;
  }

  private static Map<Ip, String> ipOwners(Map<String, Configuration> configurations) {
    Map<Ip, String> owners = new HashMap<>();
    if (configurations == null) {
      return owners;
    }
    for (Configuration configuration : configurations.values()) {
      for (Interface iface : configuration.getAllInterfaces().values()) {
        if (iface.getConcreteAddress() != null) {
          owners.put(iface.getConcreteAddress().getIp(), configuration.getHostname());
        }
      }
    }
    return owners;
  }
}
