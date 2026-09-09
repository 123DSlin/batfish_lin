package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.route.nh.NextHop;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.batfish.datamodel.route.nh.NextHopInterface;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrPolicyEndpoint;
import org.batfish.datamodel.sr.SrSegment;
import org.batfish.datamodel.sr.SrSegmentList;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.BatfishSymbolicRoutePipelineResult;
import org.batfish.minesweeper.symbolicroute.GuardedRib;
import org.batfish.minesweeper.symbolicroute.GuardedRibEntry;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicsr.GuardedSidDatabase;
import org.batfish.minesweeper.symbolicsr.GuardedSidEntry;
import org.batfish.minesweeper.symbolicsr.GuardedSrCandidate;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Builds Algorithm 2 forwarding tables from a converged guarded MAIN RIB and SR policy database.
 *
 * <p>Consumes {@link BatfishSymbolicRoutePipelineResult}; does not parse configs or {@code
 * traffic.json}.
 */
public final class GuardedTrafficForwarding {

  private GuardedTrafficForwarding() {}

  public static SymbolicTrafficForwarding from(
      TrafficGraph graph,
      BatfishSymbolicRoutePipelineResult controlPlane,
      Map<String, Configuration> configurations) {
    if (graph == null) {
      throw new IllegalArgumentException("traffic graph cannot be null");
    }
    if (controlPlane == null) {
      throw new IllegalArgumentException("control-plane result cannot be null");
    }
    Map<String, List<ForwardingRule>> ribs = new LinkedHashMap<>();
    for (Map.Entry<String, GuardedRib<AnnotatedRoute<AbstractRoute>>> entry :
        controlPlane.getMainRibNetwork().getRibs().entrySet()) {
      String router = entry.getKey();
      List<ForwardingRule> rules = new ArrayList<>();
      for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> candidate : entry.getValue().getEntries()) {
        ForwardingRule rule = toRule(graph, router, candidate);
        if (rule != null) {
          rules.add(rule);
        }
      }
      ribs.put(router, rules);
    }
    return new SymbolicTrafficForwarding(
        graph, ribs, srPolicies(graph, controlPlane, configurations), routerAddresses(configurations));
  }

  @Nullable
  private static ForwardingRule toRule(
      TrafficGraph graph, String router, GuardedRibEntry<AnnotatedRoute<AbstractRoute>> candidate) {
    AbstractRoute route = candidate.getSymbolicRoute().getRoute().getAbstractRoute();
    Prefix prefix = route.getNetwork();
    RouteGuard availability = candidate.getAvailabilityGuard();
    int preference = route.getAdministrativeCost();
    NextHop nextHop = route.getNextHop();
    if (nextHop instanceof NextHopDiscard) {
      return ForwardingRule.terminal(prefix, availability, preference);
    }
    if (nextHop instanceof NextHopInterface) {
      TrafficGraphEdge edge =
          outgoingByInterface(graph, router, ((NextHopInterface) nextHop).getInterfaceName());
      if (edge == null) {
        return ForwardingRule.terminal(prefix, availability, preference);
      }
      return ForwardingRule.direct(prefix, availability, preference, edge);
    }
    if (nextHop instanceof NextHopIp) {
      return ForwardingRule.indirect(prefix, availability, preference, ((NextHopIp) nextHop).getIp());
    }
    return null;
  }

  private static Map<String, List<SrPolicy>> srPolicies(
      TrafficGraph graph,
      BatfishSymbolicRoutePipelineResult controlPlane,
      Map<String, Configuration> configurations) {
    Map<String, Map<String, SrSegmentList>> listsByRouter = segmentLists(configurations);
    Map<String, List<SrPolicy>> policies = new LinkedHashMap<>();
    Map<String, List<SrPolicy.Path>> pathsByPolicy = new LinkedHashMap<>();
    Map<String, GuardedSrCandidate> firstCandidate = new LinkedHashMap<>();
    GuardedSidDatabase sids = controlPlane.getGuardedSidReconciler().getDatabase();
    for (GuardedSrCandidate candidate : controlPlane.getGuardedSrPolicyDatabase().getCandidates()) {
      String key = policyKey(candidate);
      firstCandidate.putIfAbsent(key, candidate);
      SrSegmentList list =
          listsByRouter
              .getOrDefault(candidate.getKey().getPolicyKey().getNode(), new HashMap<>())
              .get(candidate.getCandidate().getSegmentList());
      if (list == null) {
        continue;
      }
      List<SrPolicy.Segment> segments = toSegments(graph, candidate, list, sids);
      if (segments.isEmpty()) {
        continue;
      }
      int weight = Math.toIntExact(candidate.getCandidate().getWeight());
      pathsByPolicy
          .computeIfAbsent(key, unused -> new ArrayList<>())
          .add(new SrPolicy.Path(candidate.getKey().getCandidateName(), candidate.getSelectionGuard(), weight, segments));
    }
    for (Map.Entry<String, List<SrPolicy.Path>> entry : pathsByPolicy.entrySet()) {
      if (entry.getValue().isEmpty()) {
        continue;
      }
      GuardedSrCandidate sample = firstCandidate.get(entry.getKey());
      String router = sample.getKey().getPolicyKey().getNode();
      policies
          .computeIfAbsent(router, unused -> new ArrayList<>())
          .add(
              new SrPolicy(
                  router,
                  endpointPrefix(sample.getKey().getPolicyKey().getEndpoint()),
                  Math.toIntExact(sample.getKey().getPolicyKey().getColor()),
                  sample.getPolicyName(),
                  null,
                  entry.getValue()));
    }
    return policies;
  }

  private static List<SrPolicy.Segment> toSegments(
      TrafficGraph graph,
      GuardedSrCandidate candidate,
      SrSegmentList list,
      GuardedSidDatabase sids) {
    List<SrPolicy.Segment> segments = new ArrayList<>();
    for (SrSegment segment : list.getSegments()) {
      SrPolicy.Segment converted = toSegment(graph, candidate, segment, sids);
      if (converted == null) {
        return Collections.emptyList();
      }
      segments.add(converted);
    }
    return segments;
  }

  @Nullable
  private static SrPolicy.Segment toSegment(
      TrafficGraph graph,
      GuardedSrCandidate candidate,
      SrSegment segment,
      GuardedSidDatabase sids) {
    SrSidBindingKey binding = segment.getBindingKey();
    if (binding != null) {
      if (binding.getType() == SrSidBindingKey.Type.ADJACENCY) {
        TrafficGraphEdge edge =
            outgoingByInterface(graph, binding.getNode(), binding.getInterfaceName());
        if (edge == null || edge.getPeer() == null) {
          return null;
        }
        return SrPolicy.Segment.adjacency(
            binding.getNode(), edge.getPeer(), candidate.getAvailabilityGuard());
      }
      if (binding.getType() == SrSidBindingKey.Type.NODE
          || binding.getType() == SrSidBindingKey.Type.PREFIX) {
        return SrPolicy.Segment.node(binding.getNode());
      }
      return null;
    }
    if (segment.getSid() == null || segment.getSid().getType() != SrSidValue.Type.MPLS_LABEL) {
      return null;
    }
    GuardedSidEntry sid = sidForLabel(sids, segment.getSid().getMplsLabel());
    if (sid == null) {
      return null;
    }
    SrSidBindingKey key = sid.getBinding().getKey();
    if (key.getType() == SrSidBindingKey.Type.ADJACENCY && sid.getAdjacencyTarget() != null) {
      return SrPolicy.Segment.adjacency(
          key.getNode(), sid.getAdjacencyTarget().getNode(), sid.getAvailabilityGuard());
    }
    if (key.getType() == SrSidBindingKey.Type.NODE || key.getType() == SrSidBindingKey.Type.PREFIX) {
      return SrPolicy.Segment.node(key.getNode());
    }
    return null;
  }

  @Nullable
  static GuardedSidEntry sidForLabel(GuardedSidDatabase sids, long label) {
    GuardedSidEntry owner = null;
    for (GuardedSidEntry entry : sids.getEntries()) {
      SrSidValue value = entry.getBinding().getSid();
      if (value.getType() != SrSidValue.Type.MPLS_LABEL || value.getMplsLabel() != label) {
        continue;
      }
      if (entry.getResolverNode().equals(entry.getBinding().getKey().getNode())) {
        return entry;
      }
      if (owner == null) {
        owner = entry;
      }
    }
    return owner;
  }

  private static Prefix endpointPrefix(SrPolicyEndpoint endpoint) {
    if (endpoint.getFamily() != SrPolicyEndpoint.Family.IPV4 || endpoint.getIpv4() == null) {
      throw new IllegalArgumentException("YU traffic execution currently requires an IPv4 SR endpoint");
    }
    return Prefix.create(endpoint.getIpv4(), Prefix.MAX_PREFIX_LENGTH);
  }

  private static String policyKey(GuardedSrCandidate candidate) {
    return candidate.getKey().getPolicyKey().getNode()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getVrf()
        + "\u0000"
        + candidate.getPolicyName()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getColor();
  }

  private static Map<String, Map<String, SrSegmentList>> segmentLists(
      Map<String, Configuration> configurations) {
    Map<String, Map<String, SrSegmentList>> lists = new HashMap<>();
    if (configurations == null) {
      return lists;
    }
    for (Configuration configuration : configurations.values()) {
      SegmentRoutingConfig sr = configuration.getSegmentRoutingConfig();
      if (sr == null) {
        continue;
      }
      for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
        Map<String, SrSegmentList> named = lists.computeIfAbsent(configuration.getHostname(), unused -> new HashMap<>());
        for (SrSegmentList list : vrf.getSegmentLists()) {
          named.put(list.getKey().getName(), list);
        }
      }
    }
    return lists;
  }

  static Map<String, Ip> routerAddresses(Map<String, Configuration> configurations) {
    Map<String, Ip> addresses = new HashMap<>();
    if (configurations == null) {
      return addresses;
    }
    for (Configuration configuration : configurations.values()) {
      Ip loopback = null;
      Ip any = null;
      for (Interface iface : configuration.getAllInterfaces().values()) {
        if (iface.getConcreteAddress() == null) {
          continue;
        }
        Ip ip = iface.getConcreteAddress().getIp();
        any = ip;
        if (iface.getName().toLowerCase().contains("loopback")) {
          loopback = ip;
          break;
        }
      }
      if (loopback != null) {
        addresses.put(configuration.getHostname(), loopback);
      } else if (any != null) {
        addresses.put(configuration.getHostname(), any);
      }
    }
    return addresses;
  }

  @Nullable
  static TrafficGraphEdge outgoingByInterface(TrafficGraph graph, String router, String iface) {
    if (iface == null) {
      return null;
    }
    for (TrafficGraphEdge edge : graph.getOutgoingEdges(router)) {
      if (iface.equals(edge.getStartInterface())) {
        return edge;
      }
    }
    return null;
  }
}
