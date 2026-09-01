package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import com.google.common.graph.EndpointPair;
import com.google.common.graph.ValueGraph;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpPeerConfig;
import org.batfish.datamodel.BgpPeerConfigId;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.BgpSessionProperties;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.GenericRibReadOnly;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.NetworkConfigurations;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.datamodel.route.nh.NextHopInterface;
import org.batfish.datamodel.route.nh.NextHopIp;

/** Builds supported connected, numbered-eBGP, and IS-IS L1 input from parsed Batfish state. */
public final class BatfishParsedSnapshotPipelineInputBuilder {

  private BatfishParsedSnapshotPipelineInputBuilder() {}

  /** Builds a parsed snapshot and discovers BGP redistribution directly from its configuration. */
  @Nonnull
  public static BatfishSymbolicRoutePipelineInput build(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      Z3RouteGuardFactory guardFactory) {
    return build(
        configurations,
        concreteMainRibs,
        bgpTopology,
        IsisTopology.EMPTY,
        guardFactory,
        BatfishBgpRedistributionRuleExtractor.extract(configurations));
  }

  /** Builds a parsed snapshot and discovers BGP redistribution directly from its configuration. */
  @Nonnull
  public static BatfishSymbolicRoutePipelineInput build(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      IsisTopology isisTopology,
      Z3RouteGuardFactory guardFactory) {
    return build(
        configurations,
        concreteMainRibs,
        bgpTopology,
        isisTopology,
        guardFactory,
        BatfishBgpRedistributionRuleExtractor.extract(configurations));
  }

  @Nonnull
  public static BatfishSymbolicRoutePipelineInput build(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      Z3RouteGuardFactory guardFactory,
      Iterable<BatfishBgpRedistributionRule> redistributionRules) {
    return build(
        configurations,
        concreteMainRibs,
        bgpTopology,
        IsisTopology.EMPTY,
        guardFactory,
        redistributionRules);
  }

  /** Builds connected, numbered-eBGP, and Level-1 IS-IS inputs from normalized Batfish state. */
  @Nonnull
  public static BatfishSymbolicRoutePipelineInput build(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      IsisTopology isisTopology,
      Z3RouteGuardFactory guardFactory,
      Iterable<BatfishBgpRedistributionRule> redistributionRules) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(concreteMainRibs, "concreteMainRibs must be provided");
    requireNonNull(bgpTopology, "bgpTopology must be provided");
    TopologyLinkGuards topologyGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, guardFactory);
    BatfishIsisTopologyAdapter.Result isis =
        BatfishIsisTopologyAdapter.build(
            configurations,
            requireNonNull(isisTopology, "isisTopology must be provided"),
            topologyGuards,
            guardFactory);
    List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> mainSeeds = new ArrayList<>();
    List<SymbolicStaticRoute> recursiveStaticRoutes = new ArrayList<>();
    for (Configuration configuration : configurations.values()) {
      for (Interface iface : configuration.getAllInterfaces().values()) {
        LinkFailureKey linkFailureKey =
            topologyGuards.getKey(configuration.getHostname(), iface.getName());
        RouteGuard inferredGuard =
            topologyGuards.getGuard(configuration.getHostname(), iface.getName());
        RouteGuard guard = inferredGuard == null ? guardFactory.trueGuard() : inferredGuard;
        for (ConcreteInterfaceAddress address : iface.getAllConcreteAddresses()) {
          AnnotatedRoute<AbstractRoute> route =
              new AnnotatedRoute<>(
                  new ConnectedRoute(address.getPrefix(), iface.getName()), iface.getVrfName());
          mainSeeds.add(
              new SymbolicRouteSeed<>(
                  "connected:"
                      + configuration.getHostname()
                      + ":"
                      + iface.getName()
                      + ":"
                      + address,
                  configuration.getHostname(),
                  route,
                  guard,
                  linkFailureKey));
        }
      }
      for (Map.Entry<String, Vrf> vrfEntry : configuration.getVrfs().entrySet()) {
        String vrfName = vrfEntry.getKey();
        int staticIndex = 0;
        for (StaticRoute staticRoute : vrfEntry.getValue().getStaticRoutes()) {
          AnnotatedRoute<StaticRoute> annotatedRoute =
              new AnnotatedRoute<>(staticRoute, vrfName);
          String messageId =
              "configured:"
                  + configuration.getHostname()
                  + ":"
                  + vrfName.length()
                  + ":"
                  + vrfName
                  + ":"
                  + staticIndex++;
          if (staticRoute.getNextHop() instanceof NextHopIp) {
            recursiveStaticRoutes.add(
                new SymbolicStaticRoute(
                    messageId,
                    configuration.getHostname(),
                    annotatedRoute,
                    guardFactory.trueGuard()));
          } else {
            RouteGuard staticGuard = guardFactory.trueGuard();
            if (staticRoute.getNextHop() instanceof NextHopInterface) {
              String nextHopInterface =
                  ((NextHopInterface) staticRoute.getNextHop()).getInterfaceName();
              Interface iface = configuration.getAllInterfaces().get(nextHopInterface);
              if (iface == null || !iface.getActive() || !iface.getVrfName().equals(vrfName)) {
                continue;
              }
              RouteGuard interfaceGuard =
                  topologyGuards.getGuard(configuration.getHostname(), nextHopInterface);
              if (interfaceGuard != null) {
                staticGuard = interfaceGuard;
              }
            }
            mainSeeds.add(
                new SymbolicRouteSeed<>(
                    "static:" + messageId,
                    configuration.getHostname(),
                    widen(annotatedRoute),
                    staticGuard));
          }
        }
      }
    }

    Map<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>> normalizedRibs =
        new LinkedHashMap<>();
    concreteMainRibs.forEach(
        (router, byVrf) -> {
          Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>> ribs =
              new LinkedHashMap<>();
          ribs.putAll(byVrf);
          normalizedRibs.put(router, ribs);
        });

    List<BatfishBgpEdge> edges = new ArrayList<>();
    List<SymbolicRouteSession> sessions = new ArrayList<>();
    NetworkConfigurations networkConfigurations = NetworkConfigurations.of(configurations);
    for (EndpointPair<BgpPeerConfigId> topologyEdge : bgpTopology.edges()) {
      BgpPeerConfigId senderId = topologyEdge.source();
      BgpPeerConfigId receiverId = topologyEdge.target();
      BgpPeerConfig senderPeer =
          requireNonNull(
              networkConfigurations.getBgpPeerConfig(senderId), "sender peer must be present");
      BgpPeerConfig receiverPeer =
          requireNonNull(
              networkConfigurations.getBgpPeerConfig(receiverId), "receiver peer must be present");
      Configuration sender = configurations.get(senderId.getHostname());
      Configuration receiver = configurations.get(receiverId.getHostname());
      BgpProcess senderProcess = sender.getVrfs().get(senderId.getVrfName()).getBgpProcess();
      BgpProcess receiverProcess = receiver.getVrfs().get(receiverId.getVrfName()).getBgpProcess();
      BgpSessionProperties importProperties = bgpTopology.edgeValue(senderId, receiverId).get();
      BgpSessionProperties exportProperties = bgpTopology.edgeValue(receiverId, senderId).get();
      if (!importProperties.isEbgp()) {
        throw new IllegalArgumentException("parsed snapshot builder currently supports only eBGP");
      }
      String sessionId = sessionId(senderId, receiverId);
      Ip senderIp = requireNonNull(senderPeer.getLocalIp(), "numbered eBGP sender IP is required");
      String senderInterface =
          requireNonNull(
              interfaceForIp(sender, senderIp),
              "BGP session must resolve to a guarded L3 interface");
      LinkFailureKey linkFailureKey =
          requireNonNull(
              topologyGuards.getKey(sender.getHostname(), senderInterface),
              "BGP session must resolve to a canonical link identity");
      RouteGuard linkGuard =
          requireNonNull(
              topologyGuards.getGuard(sender.getHostname(), senderInterface),
              "BGP session must resolve to an aliveness guard");
      edges.add(
          new BatfishBgpEdge(
              sessionId,
              senderId.getVrfName(),
              receiverId.getVrfName(),
              sender,
              receiver,
              senderPeer,
              receiverPeer,
              senderProcess,
              receiverProcess,
              exportProperties,
              importProperties,
              senderIp,
              null,
              false));
      sessions.add(
          new SymbolicRouteSession(
              sessionId,
              senderId.getHostname(),
              receiverId.getHostname(),
              linkGuard,
              linkFailureKey));
    }
    return new BatfishSymbolicRoutePipelineInput(
        configurations,
        mainSeeds,
        recursiveStaticRoutes,
        redistributionRules,
        edges,
        sessions,
        isis.getEdges(),
        isis.getSessions(),
        isis.getSeeds(),
        isis.getL2Edges(),
        isis.getL2Sessions(),
        isis.getL2Seeds(),
        normalizedRibs);
  }

  private static AnnotatedRoute<AbstractRoute> widen(AnnotatedRoute<StaticRoute> route) {
    return new AnnotatedRoute<>(route.getRoute(), route.getSourceVrf());
  }

  private static String interfaceForIp(Configuration configuration, Ip localIp) {
    for (Interface iface : configuration.getAllInterfaces().values()) {
      if (iface.getAllConcreteAddresses().stream()
          .anyMatch(address -> address.getIp().equals(localIp))) {
        return iface.getName();
      }
    }
    return null;
  }

  private static String sessionId(BgpPeerConfigId sender, BgpPeerConfigId receiver) {
    return sender.getHostname()
        + ":"
        + sender.getVrfName()
        + "->"
        + receiver.getHostname()
        + ":"
        + receiver.getVrfName();
  }
}
