package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.IsisRoute.DEFAULT_METRIC;
import static org.batfish.datamodel.RoutingProtocol.ISIS_L1;
import static org.batfish.datamodel.isis.IsisInterfaceMode.PASSIVE;
import static org.batfish.datamodel.isis.IsisLevel.LEVEL_1;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.isis.IsisEdge;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.datamodel.isis.IsisTopology;

/** Converts Batfish's parser-derived IS-IS topology and interface routes into symbolic inputs. */
public final class BatfishIsisTopologyAdapter {

  /** Immutable IS-IS portion of one symbolic pipeline input. */
  public static final class Result {
    @Nonnull private final ImmutableList<BatfishIsisEdge> _edges;
    @Nonnull private final ImmutableList<SymbolicRouteSession> _sessions;
    @Nonnull private final ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> _seeds;

    private Result(
        Iterable<BatfishIsisEdge> edges,
        Iterable<SymbolicRouteSession> sessions,
        Iterable<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> seeds) {
      _edges = ImmutableList.copyOf(edges);
      _sessions = ImmutableList.copyOf(sessions);
      _seeds = ImmutableList.copyOf(seeds);
    }

    @Nonnull
    public ImmutableList<BatfishIsisEdge> getEdges() {
      return _edges;
    }

    @Nonnull
    public ImmutableList<SymbolicRouteSession> getSessions() {
      return _sessions;
    }

    @Nonnull
    public ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> getSeeds() {
      return _seeds;
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
    List<BatfishIsisEdge> edges = new ArrayList<>();
    List<SymbolicRouteSession> sessions = new ArrayList<>();
    topology.getNetwork().edges().stream()
        .sorted(Comparator.naturalOrder())
        .forEach(
            edge -> {
              if (!edge.getCircuitType().includes(LEVEL_1)) {
                return;
              }
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
              LinkFailureKey key =
                  requireNonNull(
                      topologyGuards.getKey(sender.getHostname(), senderInterface.getName()),
                      "IS-IS circuit must resolve to canonical link identity");
              if (!key.equals(
                  topologyGuards.getKey(receiver.getHostname(), receiverInterface.getName()))) {
                throw new IllegalArgumentException(
                    "both IS-IS endpoints must resolve to the same canonical link identity");
              }
              RouteGuard guard =
                  requireNonNull(
                      topologyGuards.getGuardsByKey().get(key),
                      "IS-IS circuit must resolve to an aliveness guard");
              String sessionId = sessionId(edge);
              edges.add(
                  new BatfishIsisEdge(
                      sessionId, edge, sender, receiver, senderInterface, receiverInterface));
              sessions.add(
                  new SymbolicRouteSession(
                      sessionId, sender.getHostname(), receiver.getHostname(), guard, key));
            });

    List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> seeds = new ArrayList<>();
    configurations.values().stream()
        .sorted(Comparator.comparing(Configuration::getHostname))
        .forEach(
            configuration -> addLevel1Seeds(configuration, topologyGuards, guardFactory, seeds));
    return new Result(edges, sessions, seeds);
  }

  private static void addLevel1Seeds(
      Configuration configuration,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory,
      List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> seeds) {
    configuration
        .getVrfs()
        .values()
        .forEach(
            vrf -> {
              IsisProcess process = vrf.getIsisProcess();
              if (process == null || process.getLevel1() == null) {
                return;
              }
              configuration.getActiveInterfaces(vrf.getName()).values().stream()
                  .sorted(Comparator.comparing(Interface::getName))
                  .forEach(
                      iface -> {
                        if (iface.getIsis() == null || iface.getIsis().getLevel1() == null) {
                          return;
                        }
                        IsisInterfaceLevelSettings settings = iface.getIsis().getLevel1();
                        long metric =
                            settings.getMode() == PASSIVE
                                ? 0L
                                : firstNonNull(settings.getCost(), DEFAULT_METRIC);
                        LinkFailureKey linkFailureKey =
                            topologyGuards.getKey(configuration.getHostname(), iface.getName());
                        RouteGuard originGuard;
                        if (settings.getMode() == PASSIVE) {
                          originGuard = guardFactory.trueGuard();
                        } else {
                          if (linkFailureKey == null) {
                            throw new IllegalArgumentException(
                                "active IS-IS interface must resolve to canonical link identity");
                          }
                          originGuard =
                              requireNonNull(
                                  topologyGuards.getGuardsByKey().get(linkFailureKey),
                                  "active IS-IS interface must resolve to aliveness guard");
                        }
                        for (ConcreteInterfaceAddress address : iface.getAllConcreteAddresses()) {
                          IsisRoute route =
                              IsisRoute.builder()
                                  .setAdmin(
                                      ISIS_L1.getDefaultAdministrativeCost(
                                          configuration.getConfigurationFormat()))
                                  .setArea(process.getNetAddress().getAreaIdString())
                                  .setLevel(LEVEL_1)
                                  .setMetric(metric)
                                  .setNetwork(address.getPrefix())
                                  .setNextHopIp(address.getIp())
                                  .setProtocol(ISIS_L1)
                                  .setSystemId(process.getNetAddress().getSystemIdString())
                                  .build();
                          seeds.add(
                              new SymbolicRouteSeed<>(
                                  "isis-l1-origin:"
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
            });
  }

  private static Configuration configuration(
      Map<String, Configuration> configurations, String hostname) {
    return requireNonNull(configurations.get(hostname), "IS-IS topology node must be configured");
  }

  private static String sessionId(IsisEdge edge) {
    return "isis-l1:"
        + edge.getNode1().getNode()
        + ":"
        + edge.getNode1().getInterfaceName()
        + "->"
        + edge.getNode2().getNode()
        + ":"
        + edge.getNode2().getInterfaceName();
  }
}
