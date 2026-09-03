package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Vrf;
import org.batfish.minesweeper.symbolicsr.GuardedSidReconciler;
import org.batfish.minesweeper.symbolicsr.GuardedSrPolicyReconciler;

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
    BatfishStaticRouteReconciler staticRouteReconciler =
        new BatfishStaticRouteReconciler(mainNetwork, input.getRecursiveStaticRoutes());
    staticRouteReconciler.start();

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
    SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpNetwork =
        SymbolicRouteNetworkFactory.create(
            routers,
            input.getBgpSessions(),
            ImmutableList.of(),
            new BatfishBgpProtocolAdapter(input.getBgpEdges(), input.getConcreteMainRibs()));
    mainRibReconciler.registerSource("bgp", bgpNetwork, route -> true);
    BatfishBgpRedistributionReconciler bgpRedistributionReconciler =
        new BatfishBgpRedistributionReconciler(
            input.getConfigurations(), input.getRedistributionRules(), mainNetwork, bgpNetwork);
    bgpRedistributionReconciler.start();
    SymbolicRouteConvergenceResult bgpConvergence =
        bgpRedistributionReconciler.getLastConvergence();
    GuardedSidReconciler sidReconciler =
        new GuardedSidReconciler(
            input.getConfigurations(),
            isisNetwork,
            isisL2Network,
            ImmutableList.<BatfishIsisEdge>builder()
                .addAll(input.getIsisEdges())
                .addAll(input.getIsisL2Edges())
                .build(),
            ImmutableList.<SymbolicRouteSession>builder()
                .addAll(input.getIsisSessions())
                .addAll(input.getIsisL2Sessions())
                .build());
    GuardedSrPolicyReconciler srPolicyReconciler =
        new GuardedSrPolicyReconciler(input.getConfigurations(), sidReconciler);
    return new BatfishSymbolicRoutePipelineResult(
        mainNetwork,
        bgpNetwork,
        isisNetwork,
        isisL2Network,
        levelTransitionReconciler,
        mainRibReconciler,
        bgpRedistributionReconciler,
        staticRouteReconciler,
        mainConvergence,
        bgpConvergence,
        isisConvergence,
        isisL2Convergence,
        sidReconciler,
        srPolicyReconciler,
        input.getConfigurations(),
        linkFailureKeysByGuardVariable(input));
  }

  private static Map<String, LinkFailureKey> linkFailureKeysByGuardVariable(
      BatfishSymbolicRoutePipelineInput input) {
    Map<String, LinkFailureKey> variables = new TreeMap<>();
    input
        .getMainSeeds()
        .forEach(
            seed -> registerLinkGuard(variables, seed.getGuard(), seed.getLinkFailureKey()));
    input
        .getIsisSeeds()
        .forEach(
            seed -> registerLinkGuard(variables, seed.getGuard(), seed.getLinkFailureKey()));
    input
        .getIsisL2Seeds()
        .forEach(
            seed -> registerLinkGuard(variables, seed.getGuard(), seed.getLinkFailureKey()));
    input
        .getBgpSessions()
        .forEach(
            session ->
                registerLinkGuard(
                    variables, session.getLinkGuard(), session.getLinkFailureKey()));
    input
        .getIsisSessions()
        .forEach(
            session ->
                registerLinkGuard(
                    variables, session.getLinkGuard(), session.getLinkFailureKey()));
    input
        .getIsisL2Sessions()
        .forEach(
            session ->
                registerLinkGuard(
                    variables, session.getLinkGuard(), session.getLinkFailureKey()));
    return variables;
  }

  private static void registerLinkGuard(
      Map<String, LinkFailureKey> variables,
      RouteGuard guard,
      LinkFailureKey linkFailureKey) {
    if (linkFailureKey == null) {
      return;
    }
    if (guard.getAst().getOperator() != BooleanGuardAst.Operator.VARIABLE) {
      throw new IllegalArgumentException("canonical link guard must be one Boolean variable");
    }
    String variableId =
        requireNonNull(guard.getAst().getVariableId(), "link guard variable id must be provided");
    LinkFailureKey old = variables.put(variableId, linkFailureKey);
    if (old != null && !old.equals(linkFailureKey)) {
      throw new IllegalArgumentException("one guard variable cannot identify two links");
    }
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
