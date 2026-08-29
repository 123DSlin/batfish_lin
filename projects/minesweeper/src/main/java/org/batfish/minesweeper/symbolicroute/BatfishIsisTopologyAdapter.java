package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.IsisRoute.DEFAULT_METRIC;
import static org.batfish.datamodel.Route.UNSET_ROUTE_NEXT_HOP_IP;
import static org.batfish.datamodel.RoutingProtocol.ISIS_L1;
import static org.batfish.datamodel.RoutingProtocol.ISIS_L2;
import static org.batfish.datamodel.isis.IsisInterfaceMode.PASSIVE;
import static org.batfish.datamodel.isis.IsisLevel.LEVEL_1;
import static org.batfish.datamodel.isis.IsisLevel.LEVEL_2;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.isis.IsisEdge;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisLevel;
import org.batfish.datamodel.isis.IsisLevelSettings;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.datamodel.isis.IsisTopology;

/** Converts Batfish's parser-derived IS-IS topology and interface routes into symbolic inputs. */
public final class BatfishIsisTopologyAdapter {

  /** Immutable, level-separated IS-IS portion of one symbolic pipeline input. */
  public static final class Result {
    @Nonnull private final ImmutableList<BatfishIsisEdge> _l1Edges;
    @Nonnull private final ImmutableList<SymbolicRouteSession> _l1Sessions;
    @Nonnull private final ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> _l1Seeds;
    @Nonnull private final ImmutableList<BatfishIsisEdge> _l2Edges;
    @Nonnull private final ImmutableList<SymbolicRouteSession> _l2Sessions;
    @Nonnull private final ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> _l2Seeds;

    private Result(
        Iterable<BatfishIsisEdge> l1Edges,
        Iterable<SymbolicRouteSession> l1Sessions,
        Iterable<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> l1Seeds,
        Iterable<BatfishIsisEdge> l2Edges,
        Iterable<SymbolicRouteSession> l2Sessions,
        Iterable<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> l2Seeds) {
      _l1Edges = ImmutableList.copyOf(l1Edges);
      _l1Sessions = ImmutableList.copyOf(l1Sessions);
      _l1Seeds = ImmutableList.copyOf(l1Seeds);
      _l2Edges = ImmutableList.copyOf(l2Edges);
      _l2Sessions = ImmutableList.copyOf(l2Sessions);
      _l2Seeds = ImmutableList.copyOf(l2Seeds);
    }

    /** Compatibility alias for the Stage 6.1 Level-1 edge list. */
    @Nonnull
    public ImmutableList<BatfishIsisEdge> getEdges() {
      return _l1Edges;
    }

    /** Compatibility alias for the Stage 6.1 Level-1 session list. */
    @Nonnull
    public ImmutableList<SymbolicRouteSession> getSessions() {
      return _l1Sessions;
    }

    /** Compatibility alias for the Stage 6.1 Level-1 seed list. */
    @Nonnull
    public ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> getSeeds() {
      return _l1Seeds;
    }

    @Nonnull
    public ImmutableList<BatfishIsisEdge> getL2Edges() {
      return _l2Edges;
    }

    @Nonnull
    public ImmutableList<SymbolicRouteSession> getL2Sessions() {
      return _l2Sessions;
    }

    @Nonnull
    public ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> getL2Seeds() {
      return _l2Seeds;
    }
  }

  private BatfishIsisTopologyAdapter() {}

  @Nonnull
  public static Result build(
      Map<String, Configuration> configurations,
      IsisTopology topology,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(topology, "topology must be provided");
    requireNonNull(topologyGuards, "topologyGuards must be provided");
    requireNonNull(guardFactory, "guardFactory must be provided");
    configurations.values().forEach(BatfishIsisTopologyAdapter::validateSupportedProcesses);
    List<BatfishIsisEdge> l1Edges = new ArrayList<>();
    List<SymbolicRouteSession> l1Sessions = new ArrayList<>();
    List<BatfishIsisEdge> l2Edges = new ArrayList<>();
    List<SymbolicRouteSession> l2Sessions = new ArrayList<>();
    topology.getNetwork().edges().stream()
        .sorted(Comparator.naturalOrder())
        .forEach(
            edge -> {
              if (edge.getCircuitType().includes(LEVEL_1)) {
                addEdge(configurations, topologyGuards, edge, LEVEL_1, l1Edges, l1Sessions);
              }
              if (edge.getCircuitType().includes(LEVEL_2)) {
                addEdge(configurations, topologyGuards, edge, LEVEL_2, l2Edges, l2Sessions);
              }
            });

    List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> l1Seeds = new ArrayList<>();
    List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> l2Seeds = new ArrayList<>();
    configurations.values().stream()
        .sorted(Comparator.comparing(Configuration::getHostname))
        .forEach(
            configuration -> {
              addLevelSeeds(configuration, topologyGuards, guardFactory, LEVEL_1, l1Seeds);
              addLevelSeeds(configuration, topologyGuards, guardFactory, LEVEL_2, l2Seeds);
            });
    return new Result(l1Edges, l1Sessions, l1Seeds, l2Edges, l2Sessions, l2Seeds);
  }

  private static void addLevelSeeds(
      Configuration configuration,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory,
      IsisLevel level,
      List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> seeds) {
    for (Vrf vrf : configuration.getVrfs().values()) {
      IsisProcess process = vrf.getIsisProcess();
      if (process == null || processSettings(process, level) == null) {
        continue;
      }
      configuration.getActiveInterfaces(vrf.getName()).values().stream()
          .sorted(Comparator.comparing(Interface::getName))
          .forEach(
              iface -> {
                IsisInterfaceLevelSettings settings = interfaceSettings(iface, level);
                if (settings == null) {
                  return;
                }
                long metric =
                    settings.getMode() == PASSIVE
                        ? 0L
                        : firstNonNull(settings.getCost(), DEFAULT_METRIC);
                LinkFailureKey linkFailureKey =
                    topologyGuards.getKey(configuration.getHostname(), iface.getName());
                RouteGuard originGuard =
                    originGuard(settings, linkFailureKey, topologyGuards, guardFactory);
                for (ConcreteInterfaceAddress address : iface.getAllConcreteAddresses()) {
                  IsisRoute route =
                      IsisRoute.builder()
                          .setAdmin(
                              protocol(level)
                                  .getDefaultAdministrativeCost(
                                      configuration.getConfigurationFormat()))
                          .setArea(process.getNetAddress().getAreaIdString())
                          .setLevel(level)
                          .setMetric(metric)
                          .setNetwork(address.getPrefix())
                          .setNextHopIp(address.getIp())
                          .setProtocol(protocol(level))
                          .setSystemId(process.getNetAddress().getSystemIdString())
                          .build();
                  seeds.add(
                      new SymbolicRouteSeed<>(
                          "isis-"
                              + levelName(level)
                              + "-origin:"
                              + configuration.getHostname()
                              + ":"
                              + vrf.getName()
                              + ":"
                              + iface.getName()
                              + ":"
                              + address,
                          configuration.getHostname(),
                          new AnnotatedRoute<>(route, vrf.getName()),
                          originGuard,
                          linkFailureKey));
                }
              });
      if (level == LEVEL_1 && process.getLevel2() != null && !process.getOverload()) {
        addAttachedDefault(configuration, vrf, process, guardFactory, seeds);
      }
    }
  }

  private static RouteGuard originGuard(
      IsisInterfaceLevelSettings settings,
      @Nullable LinkFailureKey linkFailureKey,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory) {
    if (settings.getMode() == PASSIVE) {
      return guardFactory.trueGuard();
    }
    if (linkFailureKey == null) {
      throw new IllegalArgumentException(
          "active IS-IS interface must resolve to canonical link identity");
    }
    return requireNonNull(
        topologyGuards.getGuardsByKey().get(linkFailureKey),
        "active IS-IS interface must resolve to aliveness guard");
  }

  private static void addAttachedDefault(
      Configuration configuration,
      Vrf vrf,
      IsisProcess process,
      Z3RouteGuardFactory guardFactory,
      List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> seeds) {
    IsisRoute attachedDefault =
        IsisRoute.builder()
            .setAdmin(ISIS_L1.getDefaultAdministrativeCost(configuration.getConfigurationFormat()))
            .setArea(process.getNetAddress().getAreaIdString())
            .setAttach(true)
            .setLevel(LEVEL_1)
            .setMetric(0L)
            .setNetwork(Prefix.ZERO)
            .setNextHopIp(UNSET_ROUTE_NEXT_HOP_IP)
            .setProtocol(ISIS_L1)
            .setSystemId(process.getNetAddress().getSystemIdString())
            .build();
    seeds.add(
        new SymbolicRouteSeed<>(
            "isis-l1-attached-default:" + configuration.getHostname() + ":" + vrf.getName(),
            configuration.getHostname(),
            new AnnotatedRoute<>(attachedDefault, vrf.getName()),
            guardFactory.trueGuard()));
  }

  private static void addEdge(
      Map<String, Configuration> configurations,
      TopologyLinkGuards topologyGuards,
      IsisEdge edge,
      IsisLevel level,
      List<BatfishIsisEdge> edges,
      List<SymbolicRouteSession> sessions) {
    Configuration sender = configuration(configurations, edge.getNode1().getNode());
    Configuration receiver = configuration(configurations, edge.getNode2().getNode());
    Interface senderInterface =
        requireNonNull(
            sender.getAllInterfaces().get(edge.getNode1().getInterfaceName()),
            "IS-IS sender interface must exist");
    Interface receiverInterface =
        requireNonNull(
            receiver.getAllInterfaces().get(edge.getNode2().getInterfaceName()),
            "IS-IS receiver interface must exist");
    if (senderInterface.getIsis() == null
        || receiverInterface.getIsis() == null
        || !senderInterface.getIsis().getPointToPoint()
        || !receiverInterface.getIsis().getPointToPoint()) {
      throw new IllegalArgumentException(
          "symbolic IS-IS currently supports only point-to-point circuits");
    }
    LinkFailureKey key =
        requireNonNull(
            topologyGuards.getKey(sender.getHostname(), senderInterface.getName()),
            "IS-IS circuit must resolve to canonical link identity");
    if (!key.equals(topologyGuards.getKey(receiver.getHostname(), receiverInterface.getName()))) {
      throw new IllegalArgumentException(
          "both IS-IS endpoints must resolve to the same canonical link identity");
    }
    RouteGuard guard =
        requireNonNull(
            topologyGuards.getGuardsByKey().get(key),
            "IS-IS circuit must resolve to an aliveness guard");
    String sessionId = sessionId(edge, level);
    edges.add(
        new BatfishIsisEdge(sessionId, edge, sender, receiver, senderInterface, receiverInterface));
    sessions.add(
        new SymbolicRouteSession(
            sessionId, sender.getHostname(), receiver.getHostname(), guard, key));
  }

  private static Configuration configuration(
      Map<String, Configuration> configurations, String hostname) {
    return requireNonNull(configurations.get(hostname), "IS-IS topology node must be configured");
  }

  private static void validateSupportedProcesses(Configuration configuration) {
    for (Vrf vrf : configuration.getVrfs().values()) {
      IsisProcess process = vrf.getIsisProcess();
      if (process == null) {
        continue;
      }
      if (process.getOverload()) {
        throw new IllegalArgumentException("symbolic IS-IS overload semantics are not implemented");
      }
      if (process.getExportPolicy() != null || !process.getGeneratedRoutes().isEmpty()) {
        throw new IllegalArgumentException(
            "symbolic IS-IS redistribution and generated routes are not implemented");
      }
    }
  }

  private static String sessionId(IsisEdge edge, IsisLevel level) {
    return "isis-"
        + levelName(level)
        + ":"
        + edge.getNode1().getNode()
        + ":"
        + edge.getNode1().getInterfaceName()
        + "->"
        + edge.getNode2().getNode()
        + ":"
        + edge.getNode2().getInterfaceName();
  }

  @Nullable
  private static IsisLevelSettings processSettings(IsisProcess process, IsisLevel level) {
    return level == LEVEL_1 ? process.getLevel1() : process.getLevel2();
  }

  @Nullable
  private static IsisInterfaceLevelSettings interfaceSettings(Interface iface, IsisLevel level) {
    if (iface.getIsis() == null) {
      return null;
    }
    return level == LEVEL_1 ? iface.getIsis().getLevel1() : iface.getIsis().getLevel2();
  }

  private static RoutingProtocol protocol(IsisLevel level) {
    return level == LEVEL_1 ? ISIS_L1 : ISIS_L2;
  }

  private static String levelName(IsisLevel level) {
    return level == LEVEL_1 ? "l1" : "l2";
  }
}
