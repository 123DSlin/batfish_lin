package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.graph.EndpointPair;
import com.google.common.graph.ValueGraph;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpPeerConfig;
import org.batfish.datamodel.BgpPeerConfigId;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.BgpSessionProperties;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.GenericRibReadOnly;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.NetworkConfigurations;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.datamodel.route.nh.NextHopInterface;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.minesweeper.smt.SmtProtocolSelection;

/** Builds supported connected, numbered-eBGP, and IS-IS L1 input from parsed Batfish state. */
public final class BatfishParsedSnapshotPipelineInputBuilder {

  private BatfishParsedSnapshotPipelineInputBuilder() {}

  /** Builds both protocol planes from the same explicit SMT run selection. */
  @Nonnull
  public static BatfishSymbolicRoutePipelineInput buildSelected(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      IsisTopology isisTopology,
      Z3RouteGuardFactory guardFactory,
      Set<SmtProtocolSelection.Family> selected) {
    requireNonNull(selected, "protocol selection must be provided");
    if (selected.isEmpty()) {
      throw new IllegalArgumentException("protocol selection must not be empty");
    }
    if (selected.contains(SmtProtocolSelection.Family.OSPF)) {
      throw new IllegalArgumentException("symbolic route pipeline does not support OSPF selection");
    }
    return buildSelectedInternal(
        configurations,
        concreteMainRibs,
        bgpTopology,
        isisTopology,
        guardFactory,
        BatfishBgpRedistributionRuleExtractor.extract(configurations),
        selected);
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
    return buildSelectedInternal(
        configurations,
        concreteMainRibs,
        bgpTopology,
        isisTopology,
        guardFactory,
        redistributionRules,
        java.util.EnumSet.of(SmtProtocolSelection.Family.BGP, SmtProtocolSelection.Family.ISIS));
  }

  private static BatfishSymbolicRoutePipelineInput buildSelectedInternal(
      Map<String, Configuration> configurations,
      Map<
              String,
              ? extends Map<String, ? extends GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs,
      ValueGraph<BgpPeerConfigId, BgpSessionProperties> bgpTopology,
      IsisTopology isisTopology,
      Z3RouteGuardFactory guardFactory,
      Iterable<BatfishBgpRedistributionRule> redistributionRules,
      Set<SmtProtocolSelection.Family> selected) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(concreteMainRibs, "concreteMainRibs must be provided");
    requireNonNull(bgpTopology, "bgpTopology must be provided");
    TopologyLinkGuards topologyGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, guardFactory);
    BatfishIsisTopologyAdapter.Result isis =
        selected.contains(SmtProtocolSelection.Family.ISIS)
            ? BatfishIsisTopologyAdapter.build(
                configurations,
                requireNonNull(isisTopology, "isisTopology must be provided"),
                topologyGuards,
                guardFactory)
            : null;
    List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> mainSeeds = new ArrayList<>();
    List<SymbolicStaticRoute> recursiveStaticRoutes = new ArrayList<>();
    for (Configuration configuration : configurations.values()) {
      mainSeeds.addAll(
          BatfishInterfaceRouteInitializer.build(configuration, topologyGuards, guardFactory));
      for (Map.Entry<String, Vrf> vrfEntry : configuration.getVrfs().entrySet()) {
        String vrfName = vrfEntry.getKey();
        int staticIndex = 0;
        for (StaticRoute staticRoute : vrfEntry.getValue().getStaticRoutes()) {
          AnnotatedRoute<StaticRoute> annotatedRoute = new AnnotatedRoute<>(staticRoute, vrfName);
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
          if (selected.contains(SmtProtocolSelection.Family.ISIS)) {
            ribs.putAll(byVrf);
          } else {
            // Never use a converged mixed-protocol RIB as a BGP-only policy oracle.
            byVrf.forEach(
                (vrf, original) -> {
                  org.batfish.dataplane.rib.Rib base = new org.batfish.dataplane.rib.Rib();
                  original.getTypedRoutes().stream()
                      .filter(
                          route -> {
                            org.batfish.datamodel.RoutingProtocol protocol =
                                route.getRoute().getProtocol();
                            return protocol == org.batfish.datamodel.RoutingProtocol.CONNECTED
                                || protocol == org.batfish.datamodel.RoutingProtocol.LOCAL
                                || protocol == org.batfish.datamodel.RoutingProtocol.STATIC;
                          })
                      .forEach(base::mergeRoute);
                  ribs.put(vrf, base);
                });
          }
          normalizedRibs.put(router, ribs);
        });

    List<BatfishBgpEdge> edges = new ArrayList<>();
    List<SymbolicRouteSession> sessions = new ArrayList<>();
    NetworkConfigurations networkConfigurations = NetworkConfigurations.of(configurations);
    for (EndpointPair<BgpPeerConfigId> topologyEdge :
        selected.contains(SmtProtocolSelection.Family.BGP)
            ? bgpTopology.edges()
            : Collections.<EndpointPair<BgpPeerConfigId>>emptySet()) {
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
        selected.contains(SmtProtocolSelection.Family.BGP)
            ? redistributionRules
            : Collections.emptyList(),
        edges,
        sessions,
        isis == null ? Collections.emptyList() : isis.getEdges(),
        isis == null ? Collections.emptyList() : isis.getSessions(),
        isis == null ? Collections.emptyList() : isis.getSeeds(),
        isis == null ? Collections.emptyList() : isis.getL2Edges(),
        isis == null ? Collections.emptyList() : isis.getL2Sessions(),
        isis == null ? Collections.emptyList() : isis.getL2Seeds(),
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
