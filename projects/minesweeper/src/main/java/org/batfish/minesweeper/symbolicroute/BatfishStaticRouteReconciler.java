package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.route.nh.NextHopIp;

/** Maintains the least fixed point of recursive next-hop-IP static routes in MAIN. */
public final class BatfishStaticRouteReconciler {

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _mainNetwork;
  @Nonnull private final ImmutableList<SymbolicStaticRoute> _staticRoutes;
  @Nonnull private final Set<SymbolicRouteKey> _ownedKeys;
  @Nonnull private Map<SymbolicStaticRoute, RouteGuard> _activeGuards;
  @Nonnull private SymbolicRouteConvergenceResult _lastConvergence;
  private boolean _started;
  private boolean _reconciling;
  private boolean _pending;

  public BatfishStaticRouteReconciler(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork,
      Iterable<SymbolicStaticRoute> staticRoutes) {
    _mainNetwork = requireNonNull(mainNetwork, "mainNetwork must be provided");
    _staticRoutes =
        ImmutableList.copyOf(requireNonNull(staticRoutes, "staticRoutes must be provided"));
    _ownedKeys = new LinkedHashSet<>();
    Map<SymbolicRouteContributionId, SymbolicStaticRoute> identities = new LinkedHashMap<>();
    Map<SymbolicStaticRoute, RouteGuard> initial = new LinkedHashMap<>();
    for (SymbolicStaticRoute route : _staticRoutes) {
      _mainNetwork.getRib(route.getRouter());
      if (!(route.getRoute().getRoute().getNextHop() instanceof NextHopIp)) {
        throw new IllegalArgumentException(
            "Batfish recursive activation requires a next-hop-IP route");
      }
      SymbolicRouteKey key = key(route);
      if (!_ownedKeys.add(key)) {
        throw new IllegalArgumentException("duplicate recursive static candidate key");
      }
      SymbolicRouteContributionId id = contributionId(route);
      if (identities.put(id, route) != null) {
        throw new IllegalArgumentException("duplicate static route contribution identity");
      }
      if (!_mainNetwork.getRib(route.getRouter()).getContributionIds(key).isEmpty()) {
        throw new IllegalArgumentException(
            "recursive static candidate is already installed before reconciliation");
      }
      RouteGuard configured = route.getConfigurationGuard();
      initial.put(route, configured.and(configured.not()).simplify());
    }
    _activeGuards = ImmutableMap.copyOf(initial);
    _lastConvergence = emptyResult();
  }

  /** Registers the MAIN stable-state callback and installs the current least fixed point. */
  public void start() {
    if (_started) {
      throw new IllegalStateException("static route reconciler is already started");
    }
    // Fail before registering a persistent callback if the initial fixed point is invalid.
    reconcile();
    _mainNetwork.getEngine().addStableStateListener(this::reconcile);
    _started = true;
    // Close the small registration window if another synchronous listener changed MAIN.
    reconcile();
  }

  /** Recomputes from a scratch base RIB and applies only semantic guard changes to MAIN. */
  public void reconcile() {
    if (_reconciling) {
      _pending = true;
      return;
    }
    _reconciling = true;
    int messages = 0;
    int withdrawals = 0;
    int updates = 0;
    try {
      do {
        _pending = false;
        Map<SymbolicStaticRoute, RouteGuard> desired = computeLeastFixedPoint();
        List<SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>>> advertisements =
            new ArrayList<>();
        List<SymbolicRouteContributionId> removals = new ArrayList<>();
        for (SymbolicStaticRoute route : _staticRoutes) {
          RouteGuard oldGuard = _activeGuards.get(route);
          RouteGuard newGuard = desired.get(route);
          if (oldGuard.isEquivalentTo(newGuard)) {
            continue;
          }
          if (!newGuard.isSatisfiable()) {
            removals.add(contributionId(route));
          } else {
            advertisements.add(message(route, newGuard));
          }
        }
        _activeGuards = ImmutableMap.copyOf(desired);
        SymbolicRouteConvergenceResult removalResult =
            removals.isEmpty() ? emptyResult() : _mainNetwork.getEngine().withdraw(removals);
        SymbolicRouteConvergenceResult advertisementResult =
            advertisements.isEmpty()
                ? emptyResult()
                : _mainNetwork.getEngine().converge(advertisements);
        messages +=
            removalResult.getProcessedMessages() + advertisementResult.getProcessedMessages();
        withdrawals +=
            removalResult.getProcessedWithdrawals() + advertisementResult.getProcessedWithdrawals();
        updates += removalResult.getRibUpdates() + advertisementResult.getRibUpdates();
      } while (_pending);
    } finally {
      _reconciling = false;
    }
    _lastConvergence = new SymbolicRouteConvergenceResult(messages, withdrawals, updates);
  }

  @Nonnull
  public ImmutableMap<SymbolicStaticRoute, RouteGuard> getActiveGuards() {
    return ImmutableMap.copyOf(_activeGuards);
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getLastConvergence() {
    return _lastConvergence;
  }

  private Map<SymbolicStaticRoute, RouteGuard> computeLeastFixedPoint() {
    List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> baseSeeds = new ArrayList<>();
    int identity = 0;
    for (Map.Entry<String, GuardedRib<AnnotatedRoute<AbstractRoute>>> byRouter :
        _mainNetwork.getRibs().entrySet()) {
      for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry :
          byRouter.getValue().getEntries()) {
        SymbolicRoute<AnnotatedRoute<AbstractRoute>> symbolic = entry.getSymbolicRoute();
        if (_ownedKeys.contains(symbolic.getKey())) {
          continue;
        }
        baseSeeds.add(
            new SymbolicRouteSeed<>(
                "static-scratch-" + identity++,
                byRouter.getKey(),
                symbolic.getRoute(),
                symbolic.getAvailabilityGuard()));
      }
    }
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> scratch =
        SymbolicRouteNetworkFactory.create(
            _mainNetwork.getRibs().keySet(),
            ImmutableList.of(),
            baseSeeds,
            new BatfishMainRibRouteAdapter());
    scratch.converge();
    return BatfishStaticRouteResolver.resolveToFixedPoint(scratch, _staticRoutes);
  }

  private static SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>> message(
      SymbolicStaticRoute route, RouteGuard guard) {
    return new SymbolicRouteSeed<>(
            route.getContributionMessageId(), route.getRouter(), widen(route.getRoute()), guard)
        .toMessage();
  }

  private static SymbolicRouteContributionId contributionId(SymbolicStaticRoute route) {
    return new SymbolicRouteContributionId(
        route.getContributionMessageId(), route.getRouter(), route.getRouter());
  }

  private static SymbolicRouteKey key(SymbolicStaticRoute route) {
    return new SymbolicRouteKey(
        route.getRouter(), route.getRoute().getSourceVrf(), widen(route.getRoute()));
  }

  private static AnnotatedRoute<AbstractRoute> widen(
      AnnotatedRoute<org.batfish.datamodel.StaticRoute> route) {
    return new AnnotatedRoute<>(route.getRoute(), route.getSourceVrf());
  }

  private static SymbolicRouteConvergenceResult emptyResult() {
    return new SymbolicRouteConvergenceResult(0, 0, 0);
  }
}
