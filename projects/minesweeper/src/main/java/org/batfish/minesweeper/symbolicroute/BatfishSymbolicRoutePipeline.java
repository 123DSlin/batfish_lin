package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.RoutingProtocol.CONNECTED;
import static org.batfish.datamodel.RoutingProtocol.STATIC;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.Vrf;

/** Executes connected/static, IS-IS L1, redistribution, and eBGP to guarded stable state. */
public final class BatfishSymbolicRoutePipeline {

  private BatfishSymbolicRoutePipeline() {}

  /** Runs the normalized fixed configuration snapshot to a whole-network symbolic fixed point. */
  @Nonnull
  public static BatfishSymbolicRoutePipelineResult run(BatfishSymbolicRoutePipelineInput input) {
    requireNonNull(input, "input must be provided");
    validate(input);
    ImmutableList<String> routers = ImmutableList.copyOf(input.getConfigurations().keySet());

    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork =
        SymbolicRouteNetworkFactory.create(
            routers, ImmutableList.of(), input.getMainSeeds(), new BatfishMainRibRouteAdapter());
    SymbolicRouteConvergenceResult mainConvergence = mainNetwork.converge();
    BatfishStaticRouteResolver.resolveToFixedPoint(mainNetwork, input.getRecursiveStaticRoutes());

    SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisNetwork =
        SymbolicRouteNetworkFactory.create(
            routers,
            input.getIsisSessions(),
            input.getIsisSeeds(),
            new BatfishIsisProtocolAdapter(input.getIsisEdges()));
    SymbolicRouteConvergenceResult isisConvergence = isisNetwork.converge();
    installSelectedIsisRoutesInMainRib(mainNetwork, isisNetwork);

    List<SymbolicRouteSeed<AnnotatedRoute<Bgpv4Route>>> bgpSeeds =
        redistributeSelectedMainRoutes(input, mainNetwork);
    SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpNetwork =
        SymbolicRouteNetworkFactory.create(
            routers,
            input.getBgpSessions(),
            bgpSeeds,
            new BatfishBgpProtocolAdapter(input.getBgpEdges(), input.getConcreteMainRibs()));
    SymbolicRouteConvergenceResult bgpConvergence = bgpNetwork.converge();
    installSelectedBgpRoutesInMainRib(mainNetwork, bgpNetwork);
    return new BatfishSymbolicRoutePipelineResult(
        mainNetwork,
        bgpNetwork,
        isisNetwork,
        mainConvergence,
        bgpConvergence,
        isisConvergence,
        input.getConfigurations());
  }

  /** Installs selected, routable IS-IS Level-1 candidates into the main RIB. */
  private static void installSelectedIsisRoutesInMainRib(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisNetwork) {
    isisNetwork
        .getRibs()
        .values()
        .forEach(
            isisRib ->
                isisRib
                    .getEntries()
                    .forEach(
                        entry -> {
                          SymbolicRoute<AnnotatedRoute<IsisRoute>> isis = entry.getSymbolicRoute();
                          if (isis.getRoute().getRoute().getNonRouting()
                              || !entry.getSelectionGuard().isSatisfiable()) {
                            return;
                          }
                          AnnotatedRoute<AbstractRoute> mainRoute =
                              new AnnotatedRoute<>(
                                  isis.getRoute().getRoute(), isis.getRoute().getSourceVrf());
                          SymbolicRouteKey mainKey =
                              new SymbolicRouteKey(
                                  isis.getKey().getRouter(), isis.getKey().getVrf(), mainRoute);
                          mainNetwork
                              .getRib(isis.getKey().getRouter())
                              .putContribution(
                                  new SymbolicRouteContributionId(
                                      "isis-l1-rib",
                                      isis.getKey().getRouter(),
                                      isis.getKey().getRouter()),
                                  new SymbolicRoute<>(
                                      mainKey,
                                      mainRoute,
                                      entry.getSelectionGuard(),
                                      isis.getProvenance()));
                        }));
  }

  /** Installs selected, routable protocol candidates into the protocol-neutral main RIB. */
  private static void installSelectedBgpRoutesInMainRib(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpNetwork) {
    bgpNetwork
        .getRibs()
        .values()
        .forEach(
            bgpRib ->
                bgpRib
                    .getEntries()
                    .forEach(
                        entry -> {
                          SymbolicRoute<AnnotatedRoute<Bgpv4Route>> bgp = entry.getSymbolicRoute();
                          if (bgp.getRoute().getRoute().getNonRouting()
                              || !entry.getSelectionGuard().isSatisfiable()) {
                            return;
                          }
                          AnnotatedRoute<AbstractRoute> mainRoute =
                              new AnnotatedRoute<>(
                                  bgp.getRoute().getRoute(), bgp.getRoute().getSourceVrf());
                          SymbolicRouteKey mainKey =
                              new SymbolicRouteKey(
                                  bgp.getKey().getRouter(), bgp.getKey().getVrf(), mainRoute);
                          mainNetwork
                              .getRib(bgp.getKey().getRouter())
                              .putContribution(
                                  new SymbolicRouteContributionId(
                                      "bgp-loc-rib",
                                      bgp.getKey().getRouter(),
                                      bgp.getKey().getRouter()),
                                  new SymbolicRoute<>(
                                      mainKey,
                                      mainRoute,
                                      entry.getSelectionGuard(),
                                      bgp.getProvenance()));
                        }));
  }

  private static List<SymbolicRouteSeed<AnnotatedRoute<Bgpv4Route>>> redistributeSelectedMainRoutes(
      BatfishSymbolicRoutePipelineInput input,
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork) {
    List<SymbolicRouteSeed<AnnotatedRoute<Bgpv4Route>>> seeds = new ArrayList<>();
    int identity = 0;
    for (BatfishBgpRedistributionRule rule : input.getRedistributionRules()) {
      Configuration configuration = input.getConfigurations().get(rule.getRouter());
      BgpProcess process = bgpProcess(configuration, rule.getTargetVrf());
      for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry :
          mainNetwork.getRib(rule.getRouter()).getEntries()) {
        SymbolicRoute<AnnotatedRoute<AbstractRoute>> symbolic = entry.getSymbolicRoute();
        RoutingProtocol sourceProtocol = symbolic.getKey().getProtocol();
        if (!symbolic.getKey().getVrf().equals(rule.getSourceVrf())
            || sourceProtocol != CONNECTED && sourceProtocol != STATIC
            || !entry.getSelectionGuard().isSatisfiable()) {
          continue;
        }
        BatfishRoutingPolicyResult<Bgpv4Route> converted =
            BatfishBgpRedistribution.redistribute(
                configuration,
                process,
                rule.getPolicyName(),
                symbolic.getRoute(),
                rule.getTargetVrf(),
                rule.getTargetProtocol());
        if (converted.getOutcome() == BatfishRoutingPolicyResult.Outcome.POLICY_NOT_FOUND) {
          throw new IllegalArgumentException(
              "redistribution policy is missing: " + rule.getPolicyName());
        }
        if (converted.getOutcome() != BatfishRoutingPolicyResult.Outcome.ACCEPTED) {
          continue;
        }
        String messageId =
            String.format(
                "pipeline-redist:%d:%s:%d",
                rule.getRuleId().length(), rule.getRuleId(), identity++);
        seeds.add(
            new SymbolicRouteSeed<>(
                messageId,
                rule.getRouter(),
                converted.getOutputRoute().get(),
                entry.getSelectionGuard()));
      }
    }
    return seeds;
  }

  private static BgpProcess bgpProcess(Configuration configuration, String vrfName) {
    Vrf vrf = configuration.getVrfs().get(vrfName);
    if (vrf == null || vrf.getBgpProcess() == null) {
      throw new IllegalArgumentException("redistribution target VRF must have a BGP process");
    }
    return vrf.getBgpProcess();
  }

  private static void validate(BatfishSymbolicRoutePipelineInput input) {
    if (input.getConfigurations().isEmpty()) {
      throw new IllegalArgumentException("at least one configuration must be provided");
    }
    for (java.util.Map.Entry<String, Configuration> entry : input.getConfigurations().entrySet()) {
      if (!entry.getKey().equals(entry.getValue().getHostname())) {
        throw new IllegalArgumentException("configuration key must equal hostname");
      }
      if (!input.getConcreteMainRibs().containsKey(entry.getKey())) {
        throw new IllegalArgumentException("every router requires concrete main-RIB contexts");
      }
    }
    Set<String> edgeIds = new HashSet<>();
    Map<String, BatfishBgpEdge> edges = new LinkedHashMap<>();
    for (BatfishBgpEdge edge : input.getBgpEdges()) {
      if (!edgeIds.add(edge.getSessionId())) {
        throw new IllegalArgumentException("duplicate BGP edge identity");
      }
      edges.put(edge.getSessionId(), edge);
      validateEdgeContext(input, edge);
    }
    Set<String> sessionIds = new HashSet<>();
    for (SymbolicRouteSession session : input.getBgpSessions()) {
      if (!sessionIds.add(session.getSessionId())) {
        throw new IllegalArgumentException("duplicate symbolic BGP session identity");
      }
      BatfishBgpEdge edge = edges.get(session.getSessionId());
      if (edge != null
          && (!session.getSender().equals(edge.getSenderConfiguration().getHostname())
              || !session.getReceiver().equals(edge.getReceiverConfiguration().getHostname()))) {
        throw new IllegalArgumentException("symbolic session endpoints must match BGP edge");
      }
    }
    if (!edgeIds.equals(sessionIds)) {
      throw new IllegalArgumentException("BGP edges and symbolic sessions must match exactly");
    }
    validateIsisInputs(input);
    Set<String> ruleIds = new HashSet<>();
    for (BatfishBgpRedistributionRule rule : input.getRedistributionRules()) {
      if (!ruleIds.add(rule.getRuleId())) {
        throw new IllegalArgumentException("duplicate redistribution rule identity");
      }
      Configuration configuration = input.getConfigurations().get(rule.getRouter());
      if (configuration == null) {
        throw new IllegalArgumentException("redistribution router must be configured");
      }
      bgpProcess(configuration, rule.getTargetVrf());
    }
    for (SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>> seed : input.getMainSeeds()) {
      if (!input.getConfigurations().containsKey(seed.getOriginRouter())) {
        throw new IllegalArgumentException("main-RIB seed router must be configured");
      }
    }
    for (SymbolicStaticRoute route : input.getRecursiveStaticRoutes()) {
      if (!input.getConfigurations().containsKey(route.getRouter())) {
        throw new IllegalArgumentException("recursive static router must be configured");
      }
    }
  }

  private static void validateIsisInputs(BatfishSymbolicRoutePipelineInput input) {
    Map<String, BatfishIsisEdge> edges = new LinkedHashMap<>();
    for (BatfishIsisEdge edge : input.getIsisEdges()) {
      if (edges.put(edge.getSessionId(), edge) != null) {
        throw new IllegalArgumentException("duplicate IS-IS edge identity");
      }
    }
    Set<String> sessions = new HashSet<>();
    for (SymbolicRouteSession session : input.getIsisSessions()) {
      if (!sessions.add(session.getSessionId())) {
        throw new IllegalArgumentException("duplicate symbolic IS-IS session identity");
      }
      BatfishIsisEdge edge = edges.get(session.getSessionId());
      if (edge == null
          || !session.getSender().equals(edge.getSenderConfiguration().getHostname())
          || !session.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
        throw new IllegalArgumentException("symbolic IS-IS session must match parsed edge");
      }
    }
    if (!edges.keySet().equals(sessions)) {
      throw new IllegalArgumentException("IS-IS edges and symbolic sessions must match exactly");
    }
    for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> seed : input.getIsisSeeds()) {
      if (!input.getConfigurations().containsKey(seed.getOriginRouter())) {
        throw new IllegalArgumentException("IS-IS seed router must be configured");
      }
    }
  }

  private static void validateEdgeContext(
      BatfishSymbolicRoutePipelineInput input, BatfishBgpEdge edge) {
    String sender = edge.getSenderConfiguration().getHostname();
    String receiver = edge.getReceiverConfiguration().getHostname();
    if (input.getConfigurations().get(sender) != edge.getSenderConfiguration()
        || input.getConfigurations().get(receiver) != edge.getReceiverConfiguration()) {
      throw new IllegalArgumentException("BGP edge configurations must come from pipeline input");
    }
    if (!hasMainRib(input, sender, edge.getSenderVrf())
        || !hasMainRib(input, receiver, edge.getReceiverVrf())) {
      throw new IllegalArgumentException("BGP edge endpoint VRFs require concrete main RIBs");
    }
  }

  private static boolean hasMainRib(
      BatfishSymbolicRoutePipelineInput input, String router, String vrf) {
    Map<String, ?> byVrf = input.getConcreteMainRibs().get(router);
    return byVrf != null && byVrf.get(vrf) != null;
  }
}
