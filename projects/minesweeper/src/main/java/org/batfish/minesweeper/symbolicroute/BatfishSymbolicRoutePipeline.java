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
    SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisL2Network =
        SymbolicRouteNetworkFactory.create(
            routers,
            input.getIsisL2Sessions(),
            input.getIsisL2Seeds(),
            new BatfishIsisProtocolAdapter(
                input.getIsisL2Edges(), org.batfish.datamodel.isis.IsisLevel.LEVEL_2));
    SymbolicRouteConvergenceResult nativeL2Convergence = isisL2Network.converge();
    BatfishIsisLevelTransitionReconciler levelTransitionReconciler =
        new BatfishIsisLevelTransitionReconciler(
            input.getConfigurations(), isisNetwork, isisL2Network);
    isisNetwork.getEngine().addStableStateListener(levelTransitionReconciler::reconcile);
    BatfishMainRibReconciler mainRibReconciler = new BatfishMainRibReconciler(mainNetwork);
    mainRibReconciler.registerSource(
        "isis-l1", isisNetwork, route -> !rejectAttachedAtL1L2Router(input, route));
    mainRibReconciler.registerSource("isis-l2", isisL2Network, route -> true);
    SymbolicRouteConvergenceResult isisConvergence = isisNetwork.converge();
    SymbolicRouteConvergenceResult transitionConvergence =
        levelTransitionReconciler.getLastConvergence();
    SymbolicRouteConvergenceResult isisL2Convergence =
        new SymbolicRouteConvergenceResult(
            nativeL2Convergence.getProcessedMessages()
                + transitionConvergence.getProcessedMessages(),
            nativeL2Convergence.getProcessedWithdrawals()
                + transitionConvergence.getProcessedWithdrawals(),
            nativeL2Convergence.getRibUpdates() + transitionConvergence.getRibUpdates());
    List<SymbolicRouteSeed<AnnotatedRoute<Bgpv4Route>>> bgpSeeds =
        redistributeSelectedMainRoutes(input, mainNetwork);
    SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpNetwork =
        SymbolicRouteNetworkFactory.create(
            routers,
            input.getBgpSessions(),
            bgpSeeds,
            new BatfishBgpProtocolAdapter(input.getBgpEdges(), input.getConcreteMainRibs()));
    SymbolicRouteConvergenceResult bgpConvergence = bgpNetwork.converge();
    mainRibReconciler.registerSource("bgp", bgpNetwork, route -> true);
    return new BatfishSymbolicRoutePipelineResult(
        mainNetwork,
        bgpNetwork,
        isisNetwork,
        isisL2Network,
        levelTransitionReconciler,
        mainRibReconciler,
        mainConvergence,
        bgpConvergence,
        isisConvergence,
        isisL2Convergence,
        input.getConfigurations());
  }

  private static boolean rejectAttachedAtL1L2Router(
      BatfishSymbolicRoutePipelineInput input, SymbolicRoute<AnnotatedRoute<IsisRoute>> route) {
    if (!route.getRoute().getRoute().getAttach()) {
      return false;
    }
    Configuration configuration = input.getConfigurations().get(route.getKey().getRouter());
    Vrf vrf = configuration.getVrfs().get(route.getKey().getVrf());
    return vrf != null && vrf.getIsisProcess() != null && vrf.getIsisProcess().getLevel2() != null;
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
    validateIsisLevelInputs(
        input, input.getIsisEdges(), input.getIsisSessions(), input.getIsisSeeds(), "L1");
    validateIsisLevelInputs(
        input, input.getIsisL2Edges(), input.getIsisL2Sessions(), input.getIsisL2Seeds(), "L2");
  }

  private static void validateIsisLevelInputs(
      BatfishSymbolicRoutePipelineInput input,
      Iterable<BatfishIsisEdge> levelEdges,
      Iterable<SymbolicRouteSession> levelSessions,
      Iterable<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> levelSeeds,
      String levelName) {
    Map<String, BatfishIsisEdge> edges = new LinkedHashMap<>();
    for (BatfishIsisEdge edge : levelEdges) {
      if (edges.put(edge.getSessionId(), edge) != null) {
        throw new IllegalArgumentException("duplicate IS-IS " + levelName + " edge identity");
      }
    }
    Set<String> sessions = new HashSet<>();
    for (SymbolicRouteSession session : levelSessions) {
      if (!sessions.add(session.getSessionId())) {
        throw new IllegalArgumentException(
            "duplicate symbolic IS-IS " + levelName + " session identity");
      }
      BatfishIsisEdge edge = edges.get(session.getSessionId());
      if (edge == null
          || !session.getSender().equals(edge.getSenderConfiguration().getHostname())
          || !session.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
        throw new IllegalArgumentException("symbolic IS-IS session must match parsed edge");
      }
    }
    if (!edges.keySet().equals(sessions)) {
      throw new IllegalArgumentException(
          "IS-IS " + levelName + " edges and symbolic sessions must match exactly");
    }
    for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> seed : levelSeeds) {
      if (!input.getConfigurations().containsKey(seed.getOriginRouter())) {
        throw new IllegalArgumentException(
            "IS-IS " + levelName + " seed router must be configured");
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
