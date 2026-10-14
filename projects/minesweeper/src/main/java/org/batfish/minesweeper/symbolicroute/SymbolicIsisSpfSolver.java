package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisLevel;

/**
 * Stable-state symbolic IS-IS SPF solver.
 *
 * <p>Unlike the legacy HoYAN route-propagation adapter, this solver never advertises a prefix route
 * hop by hop. It evaluates each guarded adjacency state, compares all simple paths by symbolic
 * accumulated cost, and compiles the SPF outcomes into guarded typed routes. The current backend is
 * exact for topologies with at most {@value #MAX_EXACT_LINKS} independent physical-link variables.
 */
public final class SymbolicIsisSpfSolver {

  private static final int MAX_EXACT_LINKS = 20;

  /** One solved level: a populated protocol network plus convergence accounting. */
  public static final class Result {
    @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _network;
    @Nonnull private final SymbolicRouteConvergenceResult _convergence;

    private Result(
        SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> network,
        SymbolicRouteConvergenceResult convergence) {
      _network = network;
      _convergence = convergence;
    }

    @Nonnull
    public SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> getNetwork() {
      return _network;
    }

    @Nonnull
    public SymbolicRouteConvergenceResult getConvergence() {
      return _convergence;
    }
  }

  private static final class OutcomeKey {
    @Nonnull private final String _installationRouter;
    @Nonnull private final AnnotatedRoute<IsisRoute> _route;
    @Nonnull private final SymbolicRouteProvenance _provenance;
    @Nonnull private final ImmutableMap<String, Integer> _costTerms;
    @Nonnull private final ImmutableMap<String, Long> _costPins;

    private OutcomeKey(
        String installationRouter,
        AnnotatedRoute<IsisRoute> route,
        SymbolicRouteProvenance provenance,
        Map<String, Integer> costTerms,
        Map<String, Long> costPins) {
      _installationRouter = installationRouter;
      _route = route;
      _provenance = provenance;
      _costTerms = ImmutableMap.copyOf(costTerms);
      _costPins = ImmutableMap.copyOf(costPins);
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof OutcomeKey)) {
        return false;
      }
      OutcomeKey that = (OutcomeKey) object;
      return _installationRouter.equals(that._installationRouter)
          && _route.equals(that._route)
          && _provenance.equals(that._provenance);
    }

    @Override
    public int hashCode() {
      return java.util.Objects.hash(_installationRouter, _route, _provenance);
    }
  }

  private static final class SpfPath {
    private final ImmutableList<BatfishIsisEdge> _edges;
    private final ImmutableMap<String, Integer> _costTerms;
    private final ImmutableMap<String, Long> _pins;

    private SpfPath(
        List<BatfishIsisEdge> edges, Map<String, Integer> costTerms, Map<String, Long> pins) {
      _edges = ImmutableList.copyOf(edges);
      _costTerms = ImmutableMap.copyOf(costTerms);
      _pins = ImmutableMap.copyOf(pins);
    }
  }

  private SymbolicIsisSpfSolver() {}

  /** Solve one IS-IS level and return a network compatible with the existing RIB pipeline. */
  @Nonnull
  public static Result solve(
      Collection<String> routers,
      Collection<BatfishIsisEdge> edges,
      Collection<SymbolicRouteSession> sessions,
      Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> originatedPrefixes,
      IsisLevel level) {
    requireNonNull(routers, "routers must be provided");
    requireNonNull(edges, "edges must be provided");
    requireNonNull(sessions, "sessions must be provided");
    requireNonNull(originatedPrefixes, "originated prefixes must be provided");
    if (level == IsisLevel.LEVEL_1_2) {
      throw new IllegalArgumentException("SPF solves one IS-IS level at a time");
    }
    if (originatedPrefixes.isEmpty()) {
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> empty =
          SymbolicRouteNetworkFactory.create(
              routers,
              ImmutableList.of(),
              ImmutableList.of(),
              new BatfishIsisProtocolAdapter(ImmutableList.of(), level, true));
      return new Result(empty, empty.converge());
    }

    Map<String, BatfishIsisEdge> edgesBySession = new LinkedHashMap<>();
    edges.forEach(edge -> edgesBySession.put(edge.getSessionId(), edge));
    Map<String, SymbolicRouteSession> sessionsById = new LinkedHashMap<>();
    sessions.forEach(session -> sessionsById.put(session.getSessionId(), session));
    if (!edgesBySession.keySet().equals(sessionsById.keySet())) {
      throw new IllegalArgumentException("IS-IS SPF edges and sessions must match");
    }

    Map<String, RouteGuard> physicalGuards = new TreeMap<>();
    sessions.forEach(
        session ->
            physicalGuards.putIfAbsent(
                requireNonNull(
                    session.getLinkGuard().getAst().getVariableId(),
                    "IS-IS link guard must be a variable"),
                session.getLinkGuard()));
    if (physicalGuards.size() > MAX_EXACT_LINKS) {
      throw new IllegalArgumentException(
          "exact symbolic SPF supports at most "
              + MAX_EXACT_LINKS
              + " link variables, found "
              + physicalGuards.size());
    }
    Map<OutcomeKey, RouteGuard> outcomes = new LinkedHashMap<>();
    List<String> variables = ImmutableList.copyOf(physicalGuards.keySet());
    long scenarioCount = 1L << variables.size();
    for (long mask = 0; mask < scenarioCount; mask++) {
      Map<String, Boolean> assignment = assignment(variables, mask);
      RouteGuard cube = scenarioCube(variables, assignment, physicalGuards, originatedPrefixes);
      Map<String, List<BatfishIsisEdge>> outgoing = aliveOutgoing(edges, sessionsById, assignment);
      collectScenarioOutcomes(
          routers, originatedPrefixes, outgoing, assignment, cube, level, outcomes);
    }

    List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> localSeeds = new ArrayList<>();
    Map<SymbolicRouteContributionId, SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> dependentSeeds =
        new LinkedHashMap<>();
    Map<SymbolicRouteContributionId, SymbolicRouteContributionId> dependencies =
        new LinkedHashMap<>();
    int id = 0;
    for (Map.Entry<OutcomeKey, RouteGuard> outcome : outcomes.entrySet()) {
      OutcomeKey key = outcome.getKey();
      String originMessageId = requireNonNull(key._provenance.getParentMessageId());
      boolean localOrigin =
          key._installationRouter.equals(key._provenance.getOriginRouter())
              && key._provenance.getRouterPath().size() == 1;
      String solvedMessageId =
          localOrigin ? originMessageId : "isis-spf-" + levelName(level) + "-" + id++;
      SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> solvedSeed =
          new SymbolicRouteSeed<>(
              solvedMessageId,
              key._installationRouter,
              key._route,
              outcome.getValue().simplify(),
              null,
              key._provenance);
      if (localOrigin) {
        localSeeds.add(solvedSeed);
      }
      if (!localOrigin) {
        SymbolicRouteContributionId child =
            new SymbolicRouteContributionId(
                solvedMessageId, key._installationRouter, key._installationRouter);
        dependencies.put(
            child,
            new SymbolicRouteContributionId(
                originMessageId,
                key._provenance.getOriginRouter(),
                key._provenance.getOriginRouter()));
        dependentSeeds.put(child, solvedSeed);
      }
    }
    SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> network =
        SymbolicRouteNetworkFactory.create(
            routers,
            ImmutableList.of(),
            localSeeds,
            new BatfishIsisProtocolAdapter(ImmutableList.of(), level, true));
    dependencies.forEach(
        (child, parent) ->
            network
                .getEngine()
                .addDependentAdvertisement(parent, dependentSeeds.get(child).toMessage()));
    return new Result(network, network.converge());
  }

  private static void collectScenarioOutcomes(
      Collection<String> routers,
      Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> prefixes,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Map<String, Boolean> assignment,
      RouteGuard cube,
      IsisLevel level,
      Map<OutcomeKey, RouteGuard> outcomes) {
    Map<String, List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>>> byPrefix =
        new LinkedHashMap<>();
    for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> prefix : prefixes) {
      if (prefix.getRoute().getRoute().getLevel() == level
          && evaluate(prefix.getGuard().getAst(), assignment)) {
        byPrefix
            .computeIfAbsent(
                prefix.getRoute().getRoute().getNetwork().toString(), unused -> new ArrayList<>())
            .add(prefix);
      }
    }
    for (List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins : byPrefix.values()) {
      Map<String, List<OutcomeKey>> candidates = new LinkedHashMap<>();
      for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> origin : origins) {
        collectOriginCandidates(routers, origin, outgoing, candidates);
      }
      for (List<OutcomeKey> routerCandidates : candidates.values()) {
        for (OutcomeKey candidate : routerCandidates) {
          RouteGuard guard = cube;
          for (OutcomeKey competitor : routerCandidates) {
            if (candidate == competitor) {
              continue;
            }
            if (candidate._costTerms.equals(competitor._costTerms)) {
              continue;
            } else {
              Map<String, Long> pins = new LinkedHashMap<>(candidate._costPins);
              competitor._costPins.forEach(
                  (name, pin) -> {
                    Long old = pins.putIfAbsent(name, pin);
                    if (old != null && !old.equals(pin)) {
                      throw new IllegalStateException("conflicting IS-IS metric pin for " + name);
                    }
                  });
              guard =
                  guard.andAst(
                      BooleanGuardAst.integerLessThanOrEqual(
                          new SymbolicIntegerComparison(
                              candidate._costTerms, competitor._costTerms, pins)));
            }
          }
          outcomes.merge(candidate, guard, RouteGuard::or);
        }
      }
    }
  }

  private static Map<String, Boolean> assignment(List<String> variables, long mask) {
    Map<String, Boolean> assignment = new LinkedHashMap<>();
    for (int i = 0; i < variables.size(); i++) {
      assignment.put(variables.get(i), (mask & (1L << i)) != 0L);
    }
    return assignment;
  }

  private static RouteGuard scenarioCube(
      List<String> variables,
      Map<String, Boolean> assignment,
      Map<String, RouteGuard> guards,
      Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> prefixes) {
    RouteGuard cube;
    if (variables.isEmpty()) {
      RouteGuard any =
          prefixes.stream()
              .map(SymbolicRouteSeed::getGuard)
              .findFirst()
              .orElseThrow(
                  () -> new IllegalArgumentException("symbolic SPF requires a seed guard"));
      return any.or(any.not());
    }
    RouteGuard first = guards.get(variables.get(0));
    cube = first.or(first.not());
    for (String variable : variables) {
      RouteGuard guard = guards.get(variable);
      cube = cube.and(Boolean.TRUE.equals(assignment.get(variable)) ? guard : guard.not());
    }
    return cube;
  }

  private static Map<String, List<BatfishIsisEdge>> aliveOutgoing(
      Collection<BatfishIsisEdge> edges,
      Map<String, SymbolicRouteSession> sessions,
      Map<String, Boolean> assignment) {
    Map<String, List<BatfishIsisEdge>> outgoing = new LinkedHashMap<>();
    for (BatfishIsisEdge edge : edges) {
      SymbolicRouteSession session = requireNonNull(sessions.get(edge.getSessionId()));
      String variable = requireNonNull(session.getLinkGuard().getAst().getVariableId());
      if (Boolean.TRUE.equals(assignment.get(variable))) {
        outgoing
            .computeIfAbsent(
                edge.getSenderConfiguration().getHostname(), unused -> new ArrayList<>())
            .add(edge);
      }
    }
    return outgoing;
  }

  private static void collectOriginCandidates(
      Collection<String> routers,
      SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> origin,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Map<String, List<OutcomeKey>> candidates) {
    String originRouter = origin.getOriginRouter();
    Map<String, Integer> originTerms = new LinkedHashMap<>();
    Map<String, Long> originPins = new LinkedHashMap<>();
    addOriginMetric(origin, outgoing, originTerms, originPins);
    Map<String, List<SpfPath>> paths = new LinkedHashMap<>();
    enumeratePaths(
        originRouter,
        originRouter,
        origin.getRoute().getRoute().getLevel(),
        outgoing,
        new LinkedHashSet<>(Collections.singleton(originRouter)),
        new ArrayList<>(),
        new LinkedHashMap<>(originTerms),
        new LinkedHashMap<>(originPins),
        paths);
    for (String router : routers) {
      if (router.equals(originRouter)) {
        SymbolicRouteProvenance provenance =
            new SymbolicRouteProvenance(
                originRouter, router, null, null, ImmutableList.of(router), origin.getMessageId());
        candidates
            .computeIfAbsent(router, unused -> new ArrayList<>())
            .add(new OutcomeKey(router, origin.getRoute(), provenance, originTerms, originPins));
        continue;
      }
      List<SpfPath> destinationPaths = paths.getOrDefault(router, Collections.emptyList());
      for (SpfPath path : destinationPaths) {
        BatfishIsisEdge predecessor = path._edges.get(path._edges.size() - 1);
        ConcreteInterfaceAddress senderAddress =
            predecessor.getSenderInterface().getConcreteAddress();
        if (senderAddress == null) {
          throw new IllegalArgumentException("numbered IS-IS point-to-point interface is required");
        }
        List<String> routerPath = new ArrayList<>();
        routerPath.add(originRouter);
        path._edges.forEach(edge -> routerPath.add(edge.getReceiverConfiguration().getHostname()));
        IsisRoute route =
            origin.getRoute().getRoute().toBuilder()
                .setAdmin(
                    origin
                        .getRoute()
                        .getRoute()
                        .getProtocol()
                        .getDefaultAdministrativeCost(
                            predecessor.getReceiverConfiguration().getConfigurationFormat()))
                .setMetric(pinnedCost(path))
                .setNextHopIp(senderAddress.getIp())
                .setNonRouting(false)
                .build();
        SymbolicRouteProvenance provenance =
            new SymbolicRouteProvenance(
                originRouter,
                router,
                predecessor.getSenderConfiguration().getHostname(),
                predecessor.getReceiverInterface().getName(),
                routerPath,
                origin.getMessageId());
        OutcomeKey key =
            new OutcomeKey(
                router,
                new AnnotatedRoute<>(route, predecessor.getReceiverInterface().getVrfName()),
                provenance,
                path._costTerms,
                path._pins);
        candidates.computeIfAbsent(router, unused -> new ArrayList<>()).add(key);
      }
    }
  }

  private static void enumeratePaths(
      String origin,
      String current,
      IsisLevel level,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Set<String> visited,
      List<BatfishIsisEdge> edges,
      Map<String, Integer> terms,
      Map<String, Long> pins,
      Map<String, List<SpfPath>> paths) {
    if (!current.equals(origin)) {
      paths
          .computeIfAbsent(current, unused -> new ArrayList<>())
          .add(new SpfPath(edges, terms, pins));
    }
    for (BatfishIsisEdge edge : outgoing.getOrDefault(current, Collections.emptyList())) {
      String receiver = edge.getReceiverConfiguration().getHostname();
      if (!visited.add(receiver)) {
        continue;
      }
      IsisInterfaceLevelSettings settings =
          level == IsisLevel.LEVEL_1
              ? edge.getReceiverInterface().getIsis().getLevel1()
              : edge.getReceiverInterface().getIsis().getLevel2();
      long pin = firstNonNull(settings.getCost(), IsisRoute.DEFAULT_METRIC);
      String variable = metricConfigVariable(edge, level);
      edges.add(edge);
      terms.merge(variable, 1, Integer::sum);
      Long oldPin = pins.putIfAbsent(variable, pin);
      if (oldPin != null && oldPin != pin) {
        throw new IllegalStateException("conflicting IS-IS metric pin for " + variable);
      }
      enumeratePaths(origin, receiver, level, outgoing, visited, edges, terms, pins, paths);
      edges.remove(edges.size() - 1);
      if (terms.compute(variable, (unused, count) -> count == 1 ? null : count - 1) == null) {
        pins.remove(variable);
      }
      visited.remove(receiver);
    }
  }

  private static void addOriginMetric(
      SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> origin,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Map<String, Integer> terms,
      Map<String, Long> pins) {
    long metric = origin.getRoute().getRoute().getMetric();
    if (metric == 0L) {
      return; // passive/loopback prefix
    }
    String router = origin.getOriginRouter();
    for (BatfishIsisEdge edge : outgoing.getOrDefault(router, Collections.emptyList())) {
      ConcreteInterfaceAddress address = edge.getSenderInterface().getConcreteAddress();
      if (address != null
          && address.getIp().equals(origin.getRoute().getRoute().getNextHopIp())
          && address.getPrefix().equals(origin.getRoute().getRoute().getNetwork())) {
        String variable =
            metricConfigVariable(
                router,
                edge.getSenderInterface().getName(),
                origin.getRoute().getRoute().getLevel());
        terms.put(variable, 1);
        pins.put(variable, metric);
        return;
      }
    }
    throw new IllegalArgumentException(
        "active IS-IS origin interface not found for " + origin.getMessageId());
  }

  private static long pinnedCost(SpfPath path) {
    long result = 0L;
    for (Map.Entry<String, Integer> term : path._costTerms.entrySet()) {
      result =
          Math.addExact(result, Math.multiplyExact(path._pins.get(term.getKey()), term.getValue()));
    }
    return result;
  }

  /** SpecLens-compatible interface metric identity. */
  public static String metricConfigVariable(BatfishIsisEdge edge, IsisLevel level) {
    return metricConfigVariable(
        edge.getReceiverConfiguration().getHostname(),
        edge.getReceiverInterface().getName(),
        level);
  }

  private static String metricConfigVariable(String router, String iface, IsisLevel level) {
    return "Config_"
        + sanitize(router)
        + "_Interface_"
        + sanitize(iface)
        + "_Isis_"
        + (level == IsisLevel.LEVEL_1 ? "L1" : "L2")
        + "_cost";
  }

  private static String sanitize(String raw) {
    return raw.replaceAll("[^A-Za-z0-9_]", "_");
  }

  private static boolean evaluate(BooleanGuardAst ast, Map<String, Boolean> assignment) {
    switch (ast.getOperator()) {
      case TRUE:
        return true;
      case FALSE:
        return false;
      case VARIABLE:
        return Boolean.TRUE.equals(assignment.get(ast.getVariableId()));
      case NOT:
        return !evaluate(ast.getChildren().get(0), assignment);
      case AND:
        return ast.getChildren().stream().allMatch(child -> evaluate(child, assignment));
      case OR:
        return ast.getChildren().stream().anyMatch(child -> evaluate(child, assignment));
      default:
        throw new IllegalArgumentException("unsupported IS-IS guard operator");
    }
  }

  private static String levelName(IsisLevel level) {
    return level == IsisLevel.LEVEL_1 ? "l1" : "l2";
  }
}
