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
import java.util.Objects;
import java.util.Optional;
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
    @Nonnull private final StableState _stableState;

    private Result(
        SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> network,
        SymbolicRouteConvergenceResult convergence,
        StableState stableState) {
      _network = network;
      _convergence = convergence;
      _stableState = stableState;
    }

    @Nonnull
    public SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> getNetwork() {
      return _network;
    }

    @Nonnull
    public SymbolicRouteConvergenceResult getConvergence() {
      return _convergence;
    }

    /** Mutable SPF stable state used when cross-level origins change. */
    @Nonnull
    public StableState getStableState() {
      return _stableState;
    }
  }

  private static final class SolvedKey {
    @Nonnull private final String _installationRouter;
    @Nonnull private final String _originMessageId;
    @Nonnull private final String _sourceVrf;
    @Nonnull private final String _network;
    @Nonnull private final ImmutableList<String> _routerPath;

    private SolvedKey(OutcomeKey outcome) {
      _installationRouter = outcome._installationRouter;
      _originMessageId = requireNonNull(outcome._provenance.getParentMessageId());
      _sourceVrf = outcome._route.getSourceVrf();
      _network = outcome._route.getNetwork().toString();
      _routerPath = ImmutableList.copyOf(outcome._provenance.getRouterPath());
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof SolvedKey)) {
        return false;
      }
      SolvedKey that = (SolvedKey) object;
      return _installationRouter.equals(that._installationRouter)
          && _originMessageId.equals(that._originMessageId)
          && _sourceVrf.equals(that._sourceVrf)
          && _network.equals(that._network)
          && _routerPath.equals(that._routerPath);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_installationRouter, _originMessageId, _sourceVrf, _network, _routerPath);
    }
  }

  private static final class ActiveSolvedRoute {
    @Nonnull private final SymbolicRouteContributionId _contributionId;
    @Nonnull private final AnnotatedRoute<IsisRoute> _route;
    @Nonnull private final RouteGuard _guard;

    private ActiveSolvedRoute(
        SymbolicRouteContributionId contributionId,
        AnnotatedRoute<IsisRoute> route,
        RouteGuard guard) {
      _contributionId = contributionId;
      _route = route;
      _guard = guard;
    }
  }

  /** Symbolic accumulated IS-IS metric attached to one stable SPF contribution. */
  public static final class MetricExpression {
    @Nonnull private final ImmutableMap<String, Integer> _terms;
    @Nonnull private final ImmutableMap<String, Long> _pins;
    private final long _constant;

    private MetricExpression(Map<String, Integer> terms, Map<String, Long> pins, long constant) {
      _terms = ImmutableMap.copyOf(terms);
      _pins = ImmutableMap.copyOf(pins);
      _constant = constant;
    }
  }

  private static final class SolvedRoute {
    @Nonnull private final SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> _seed;
    @Nonnull private final MetricExpression _metric;

    private SolvedRoute(
        SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> seed, MetricExpression metric) {
      _seed = seed;
      _metric = metric;
    }
  }

  /**
   * Recomputable stable-state backend for one IS-IS level.
   *
   * <p>Callers replace the complete set of LSP prefix origins. The backend runs SPF over all of
   * them together and reconciles the resulting stable routes into the same RIB objects.
   */
  public static final class StableState {
    @Nonnull private final ImmutableList<String> _routers;
    @Nonnull private final ImmutableList<BatfishIsisEdge> _edges;
    @Nonnull private final ImmutableList<SymbolicRouteSession> _sessions;
    @Nonnull private final IsisLevel _level;
    @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _network;
    @Nonnull private final Map<SolvedKey, String> _messageIds;
    @Nonnull private final Map<SolvedKey, ActiveSolvedRoute> _active;
    @Nonnull private final Map<SymbolicRouteContributionId, MetricExpression> _metricExpressions;
    @Nonnull private final Map<String, MetricExpression> _knownOriginMetrics;
    private boolean _reconciling;

    private StableState(
        Collection<String> routers,
        Collection<BatfishIsisEdge> edges,
        Collection<SymbolicRouteSession> sessions,
        IsisLevel level) {
      _routers = ImmutableList.copyOf(routers);
      _edges = ImmutableList.copyOf(edges);
      _sessions = ImmutableList.copyOf(sessions);
      _level = level;
      _network =
          SymbolicRouteNetworkFactory.create(
              _routers,
              ImmutableList.of(),
              ImmutableList.of(),
              new BatfishIsisProtocolAdapter(ImmutableList.of(), level, true));
      _messageIds = new LinkedHashMap<>();
      _active = new LinkedHashMap<>();
      _metricExpressions = new LinkedHashMap<>();
      _knownOriginMetrics = new LinkedHashMap<>();
      _reconciling = false;
      _network.getEngine().addStableStateListener(this::reconcileExternalOriginChanges);
    }

    @Nonnull
    public SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> getNetwork() {
      return _network;
    }

    /** Atomically reconciles the SPF result for the complete current set of origins. */
    @Nonnull
    public SymbolicRouteConvergenceResult reconcileOrigins(
        Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins) {
      return reconcileOrigins(origins, ImmutableMap.of());
    }

    @Nonnull
    SymbolicRouteConvergenceResult reconcileOrigins(
        Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins,
        Map<String, MetricExpression> inheritedMetrics) {
      if (_reconciling) {
        return new SymbolicRouteConvergenceResult(0, 0, 0);
      }
      _reconciling = true;
      try {
        return reconcileOriginsInternal(origins, inheritedMetrics);
      } finally {
        _reconciling = false;
      }
    }

    @Nonnull
    private SymbolicRouteConvergenceResult reconcileOriginsInternal(
        Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins,
        Map<String, MetricExpression> inheritedMetrics) {
      Map<SolvedKey, SolvedRoute> desired =
          computeSolvedRoutes(
              _routers, _edges, _sessions, origins, inheritedMetrics, _level, _messageIds);
      List<SymbolicRouteContributionId> withdrawals = new ArrayList<>();
      for (Map.Entry<SolvedKey, ActiveSolvedRoute> active : _active.entrySet()) {
        SolvedRoute next = desired.get(active.getKey());
        if (next == null || !active.getValue()._route.equals(next._seed.getRoute())) {
          withdrawals.add(active.getValue()._contributionId);
        }
      }
      SymbolicRouteConvergenceResult withdrawn =
          withdrawals.isEmpty()
              ? new SymbolicRouteConvergenceResult(0, 0, 0)
              : _network.getEngine().withdraw(withdrawals);
      List<SymbolicRouteMessage<AnnotatedRoute<IsisRoute>>> advertisements = new ArrayList<>();
      Map<SolvedKey, ActiveSolvedRoute> nextActive = new LinkedHashMap<>();
      Map<SymbolicRouteContributionId, MetricExpression> nextMetrics = new LinkedHashMap<>();
      for (Map.Entry<SolvedKey, SolvedRoute> entry : desired.entrySet()) {
        SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> next = entry.getValue()._seed;
        ActiveSolvedRoute previous = _active.get(entry.getKey());
        SymbolicRouteContributionId contributionId =
            new SymbolicRouteContributionId(
                next.getMessageId(), next.getOriginRouter(), next.getOriginRouter());
        if (previous == null
            || !previous._route.equals(next.getRoute())
            || !previous._guard.isEquivalentTo(next.getGuard())) {
          advertisements.add(next.toMessage());
        }
        nextActive.put(
            entry.getKey(),
            new ActiveSolvedRoute(contributionId, next.getRoute(), next.getGuard()));
        nextMetrics.put(contributionId, entry.getValue()._metric);
      }
      _active.clear();
      _active.putAll(nextActive);
      _metricExpressions.clear();
      _metricExpressions.putAll(nextMetrics);
      desired.forEach(
          (key, value) -> {
            if (key._installationRouter.equals(value._seed.getOriginRouter())
                && key._routerPath.size() == 1) {
              _knownOriginMetrics.put(key._originMessageId, value._metric);
            }
          });
      SymbolicRouteConvergenceResult advertised =
          advertisements.isEmpty()
              ? new SymbolicRouteConvergenceResult(0, 0, 0)
              : _network.getEngine().converge(advertisements);
      return new SymbolicRouteConvergenceResult(
          withdrawn.getProcessedMessages() + advertised.getProcessedMessages(),
          withdrawn.getProcessedWithdrawals() + advertised.getProcessedWithdrawals(),
          withdrawn.getRibUpdates() + advertised.getRibUpdates());
    }

    private void reconcileExternalOriginChanges() {
      if (_reconciling) {
        return;
      }
      List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins = new ArrayList<>();
      Map<String, MetricExpression> inherited = new LinkedHashMap<>();
      for (Map.Entry<String, GuardedRib<AnnotatedRoute<IsisRoute>>> routerRib :
          _network.getRibs().entrySet()) {
        GuardedRib<AnnotatedRoute<IsisRoute>> rib = routerRib.getValue();
        for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry : rib.getEntries()) {
          for (Map.Entry<SymbolicRouteContributionId, GuardedRibEntry<AnnotatedRoute<IsisRoute>>>
              contribution :
                  rib.getContributionEntries(entry.getSymbolicRoute().getKey()).entrySet()) {
            SymbolicRoute<AnnotatedRoute<IsisRoute>> route =
                contribution.getValue().getSymbolicRoute();
            if (route.getProvenance().getRouterPath().size() != 1
                || !route.getProvenance().getOriginRouter().equals(routerRib.getKey())) {
              continue;
            }
            String messageId = contribution.getKey().getMessageId();
            origins.add(
                new SymbolicRouteSeed<>(
                    messageId, routerRib.getKey(), route.getRoute(), route.getAvailabilityGuard()));
            MetricExpression metric = _metricExpressions.get(contribution.getKey());
            if (metric == null) {
              metric = _knownOriginMetrics.get(messageId);
            }
            if (metric == null) {
              metric =
                  new MetricExpression(
                      ImmutableMap.of(),
                      ImmutableMap.of(),
                      route.getRoute().getRoute().getMetric());
            }
            inherited.put(messageId, metric);
          }
        }
      }
      reconcileOrigins(origins, inherited);
    }

    /** Returns the accumulated metric expression for one installed SPF contribution. */
    @Nonnull
    public Optional<MetricExpression> getMetricExpression(
        SymbolicRouteContributionId contributionId) {
      return Optional.ofNullable(_metricExpressions.get(contributionId));
    }
  }

  private static final class OutcomeKey {
    @Nonnull private final String _installationRouter;
    @Nonnull private final AnnotatedRoute<IsisRoute> _route;
    @Nonnull private final SymbolicRouteProvenance _provenance;
    @Nonnull private final ImmutableMap<String, Integer> _costTerms;
    @Nonnull private final ImmutableMap<String, Long> _costPins;
    @Nonnull private final RouteGuard _originGuard;
    private final long _constantCost;

    private OutcomeKey(
        String installationRouter,
        AnnotatedRoute<IsisRoute> route,
        SymbolicRouteProvenance provenance,
        Map<String, Integer> costTerms,
        Map<String, Long> costPins,
        RouteGuard originGuard,
        long constantCost) {
      _installationRouter = installationRouter;
      _route = route;
      _provenance = provenance;
      _costTerms = ImmutableMap.copyOf(costTerms);
      _costPins = ImmutableMap.copyOf(costPins);
      _originGuard = originGuard;
      _constantCost = constantCost;
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
    private final long _constantCost;

    private SpfPath(
        List<BatfishIsisEdge> edges,
        Map<String, Integer> costTerms,
        Map<String, Long> pins,
        long constantCost) {
      _edges = ImmutableList.copyOf(edges);
      _costTerms = ImmutableMap.copyOf(costTerms);
      _pins = ImmutableMap.copyOf(pins);
      _constantCost = constantCost;
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
    StableState stableState = new StableState(routers, edges, sessions, level);
    SymbolicRouteConvergenceResult convergence = stableState.reconcileOrigins(originatedPrefixes);
    return new Result(stableState.getNetwork(), convergence, stableState);
  }

  @Nonnull
  private static Map<SolvedKey, SolvedRoute> computeSolvedRoutes(
      Collection<String> routers,
      Collection<BatfishIsisEdge> edges,
      Collection<SymbolicRouteSession> sessions,
      Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> originatedPrefixes,
      Map<String, MetricExpression> inheritedMetrics,
      IsisLevel level,
      Map<SolvedKey, String> messageIds) {
    if (originatedPrefixes.isEmpty()) {
      return ImmutableMap.of();
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
          routers,
          originatedPrefixes,
          inheritedMetrics,
          edges,
          outgoing,
          assignment,
          cube,
          level,
          outcomes);
    }
    Map<SolvedKey, SolvedRoute> solved = new LinkedHashMap<>();
    for (Map.Entry<OutcomeKey, RouteGuard> outcome : outcomes.entrySet()) {
      OutcomeKey key = outcome.getKey();
      SolvedKey solvedKey = new SolvedKey(key);
      boolean localOrigin =
          key._installationRouter.equals(key._provenance.getOriginRouter())
              && key._provenance.getRouterPath().size() == 1;
      String solvedMessageId =
          messageIds.computeIfAbsent(
              solvedKey,
              unused ->
                  localOrigin
                      ? requireNonNull(key._provenance.getParentMessageId())
                      : "isis-spf-" + levelName(level) + "-" + messageIds.size());
      SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> solvedSeed =
          new SymbolicRouteSeed<>(
              solvedMessageId,
              key._installationRouter,
              key._route,
              outcome.getValue().simplify(),
              null,
              key._provenance);
      SolvedRoute old =
          solved.put(
              solvedKey,
              new SolvedRoute(
                  solvedSeed,
                  new MetricExpression(key._costTerms, key._costPins, key._constantCost)));
      if (old != null) {
        throw new IllegalStateException("one symbolic SPF path produced multiple stable routes");
      }
    }
    return solved;
  }

  private static void collectScenarioOutcomes(
      Collection<String> routers,
      Collection<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> prefixes,
      Map<String, MetricExpression> inheritedMetrics,
      Collection<BatfishIsisEdge> allEdges,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Map<String, Boolean> assignment,
      RouteGuard cube,
      IsisLevel level,
      Map<OutcomeKey, RouteGuard> outcomes) {
    Map<String, List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>>> byPrefix =
        new LinkedHashMap<>();
    for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> prefix : prefixes) {
      BooleanGuardAst restrictedAst = restrict(prefix.getGuard().getAst(), assignment);
      if (prefix.getRoute().getRoute().getLevel() == level
          && restrictedAst.getOperator() != BooleanGuardAst.Operator.FALSE) {
        RouteGuard restrictedGuard = prefix.getGuard().withAst(restrictedAst);
        SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> restrictedPrefix =
            new SymbolicRouteSeed<>(
                prefix.getMessageId(),
                prefix.getOriginRouter(),
                prefix.getRoute(),
                restrictedGuard,
                prefix.getLinkFailureKey());
        byPrefix
            .computeIfAbsent(
                prefix.getRoute().getRoute().getNetwork().toString(), unused -> new ArrayList<>())
            .add(restrictedPrefix);
      }
    }
    for (List<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> origins : byPrefix.values()) {
      Map<String, List<OutcomeKey>> candidates = new LinkedHashMap<>();
      for (SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> origin : origins) {
        collectOriginCandidates(
            routers,
            origin,
            inheritedMetrics.get(origin.getMessageId()),
            allEdges,
            outgoing,
            candidates);
      }
      for (List<OutcomeKey> routerCandidates : candidates.values()) {
        for (OutcomeKey candidate : routerCandidates) {
          RouteGuard guard = cube.and(candidate._originGuard);
          for (OutcomeKey competitor : routerCandidates) {
            if (candidate == competitor) {
              continue;
            }
            if (candidate._costTerms.equals(competitor._costTerms)
                && candidate._constantCost == competitor._constantCost) {
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
              RouteGuard candidateNoWorse =
                  guard.withAst(
                      BooleanGuardAst.integerLessThanOrEqual(
                          new SymbolicIntegerComparison(
                              candidate._costTerms,
                              competitor._costTerms,
                              pins,
                              candidate._constantCost,
                              competitor._constantCost)));
              guard = guard.and(competitor._originGuard.not().or(candidateNoWorse));
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
      return any.withAst(BooleanGuardAst.trueValue());
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
      MetricExpression inheritedMetric,
      Collection<BatfishIsisEdge> allEdges,
      Map<String, List<BatfishIsisEdge>> outgoing,
      Map<String, List<OutcomeKey>> candidates) {
    String originRouter = origin.getOriginRouter();
    Map<String, Integer> originTerms = new LinkedHashMap<>();
    Map<String, Long> originPins = new LinkedHashMap<>();
    long originConstant =
        addOriginMetric(origin, inheritedMetric, allEdges, originTerms, originPins);
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
        originConstant,
        paths);
    for (String router : routers) {
      if (router.equals(originRouter)) {
        SymbolicRouteProvenance provenance =
            new SymbolicRouteProvenance(
                originRouter, router, null, null, ImmutableList.of(router), origin.getMessageId());
        candidates
            .computeIfAbsent(router, unused -> new ArrayList<>())
            .add(
                new OutcomeKey(
                    router,
                    origin.getRoute(),
                    provenance,
                    originTerms,
                    originPins,
                    origin.getGuard(),
                    originConstant));
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
                path._pins,
                origin.getGuard(),
                path._constantCost);
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
      long constantCost,
      Map<String, List<SpfPath>> paths) {
    if (!current.equals(origin)) {
      paths
          .computeIfAbsent(current, unused -> new ArrayList<>())
          .add(new SpfPath(edges, terms, pins, constantCost));
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
      enumeratePaths(
          origin, receiver, level, outgoing, visited, edges, terms, pins, constantCost, paths);
      edges.remove(edges.size() - 1);
      if (terms.compute(variable, (unused, count) -> count == 1 ? null : count - 1) == null) {
        pins.remove(variable);
      }
      visited.remove(receiver);
    }
  }

  private static long addOriginMetric(
      SymbolicRouteSeed<AnnotatedRoute<IsisRoute>> origin,
      MetricExpression inheritedMetric,
      Collection<BatfishIsisEdge> allEdges,
      Map<String, Integer> terms,
      Map<String, Long> pins) {
    if (inheritedMetric != null) {
      terms.putAll(inheritedMetric._terms);
      pins.putAll(inheritedMetric._pins);
      return inheritedMetric._constant;
    }
    long metric = origin.getRoute().getRoute().getMetric();
    if (metric == 0L) {
      return 0L; // passive/loopback prefix
    }
    String router = origin.getOriginRouter();
    for (BatfishIsisEdge edge : allEdges) {
      if (!edge.getSenderConfiguration().getHostname().equals(router)) {
        continue;
      }
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
        return 0L;
      }
    }
    throw new IllegalArgumentException(
        "active IS-IS origin interface not found for " + origin.getMessageId());
  }

  private static long pinnedCost(SpfPath path) {
    long result = path._constantCost;
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

  private static BooleanGuardAst restrict(BooleanGuardAst ast, Map<String, Boolean> assignment) {
    switch (ast.getOperator()) {
      case TRUE:
      case FALSE:
      case INT_LE:
        return ast;
      case VARIABLE:
        Boolean value = assignment.get(ast.getVariableId());
        return value == null
            ? ast
            : value ? BooleanGuardAst.trueValue() : BooleanGuardAst.falseValue();
      case NOT:
        BooleanGuardAst child = restrict(ast.getChildren().get(0), assignment);
        if (child.getOperator() == BooleanGuardAst.Operator.TRUE) {
          return BooleanGuardAst.falseValue();
        }
        if (child.getOperator() == BooleanGuardAst.Operator.FALSE) {
          return BooleanGuardAst.trueValue();
        }
        return BooleanGuardAst.not(child);
      case AND:
        BooleanGuardAst conjunction = BooleanGuardAst.trueValue();
        for (BooleanGuardAst conjunct : ast.getChildren()) {
          BooleanGuardAst restricted = restrict(conjunct, assignment);
          if (restricted.getOperator() == BooleanGuardAst.Operator.FALSE) {
            return BooleanGuardAst.falseValue();
          }
          if (restricted.getOperator() != BooleanGuardAst.Operator.TRUE) {
            conjunction =
                conjunction.getOperator() == BooleanGuardAst.Operator.TRUE
                    ? restricted
                    : BooleanGuardAst.and(conjunction, restricted);
          }
        }
        return conjunction;
      case OR:
        BooleanGuardAst disjunction = BooleanGuardAst.falseValue();
        for (BooleanGuardAst disjunct : ast.getChildren()) {
          BooleanGuardAst restricted = restrict(disjunct, assignment);
          if (restricted.getOperator() == BooleanGuardAst.Operator.TRUE) {
            return BooleanGuardAst.trueValue();
          }
          if (restricted.getOperator() != BooleanGuardAst.Operator.FALSE) {
            disjunction =
                disjunction.getOperator() == BooleanGuardAst.Operator.FALSE
                    ? restricted
                    : BooleanGuardAst.or(disjunction, restricted);
          }
        }
        return disjunction;
      default:
        throw new IllegalArgumentException("unsupported IS-IS guard operator");
    }
  }

  private static String levelName(IsisLevel level) {
    return level == IsisLevel.LEVEL_1 ? "l1" : "l2";
  }
}
