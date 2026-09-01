package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Predicate;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AbstractRouteDecorator;
import org.batfish.datamodel.AnnotatedRoute;

/** Reconciles selected protocol-RIB branches into the protocol-neutral guarded MAIN RIB. */
public final class BatfishMainRibReconciler {

  private static final class SourceKey {
    @Nonnull private final String _plane;
    @Nonnull private final SymbolicRouteKey _routeKey;
    @Nonnull private final SymbolicRouteContributionId _sourceContributionId;

    private SourceKey(
        String plane, SymbolicRouteKey routeKey, SymbolicRouteContributionId sourceContributionId) {
      _plane = plane;
      _routeKey = routeKey;
      _sourceContributionId = sourceContributionId;
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof SourceKey)) {
        return false;
      }
      SourceKey that = (SourceKey) object;
      return _plane.equals(that._plane)
          && _routeKey.equals(that._routeKey)
          && _sourceContributionId.equals(that._sourceContributionId);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_plane, _routeKey, _sourceContributionId);
    }
  }

  private static final class DesiredMainRoute {
    @Nonnull private final AnnotatedRoute<AbstractRoute> _route;
    @Nonnull private final RouteGuard _guard;
    @Nonnull private final SymbolicRouteProvenance _provenance;

    private DesiredMainRoute(
        AnnotatedRoute<AbstractRoute> route, RouteGuard guard, SymbolicRouteProvenance provenance) {
      _route = route;
      _guard = guard;
      _provenance = provenance;
    }
  }

  private static final class ActiveMainRoute {
    @Nonnull private final SymbolicRouteContributionId _contributionId;
    @Nonnull private final AnnotatedRoute<AbstractRoute> _route;
    @Nonnull private final RouteGuard _guard;

    private ActiveMainRoute(
        SymbolicRouteContributionId contributionId,
        AnnotatedRoute<AbstractRoute> route,
        RouteGuard guard) {
      _contributionId = contributionId;
      _route = route;
      _guard = guard;
    }
  }

  private interface Source {
    void collect(Map<SourceKey, DesiredMainRoute> desired);
  }

  private static final class TypedSource<R extends AbstractRouteDecorator> implements Source {
    @Nonnull private final String _plane;
    @Nonnull private final SymbolicRouteNetwork<R> _network;
    @Nonnull private final Predicate<SymbolicRoute<R>> _eligible;

    private TypedSource(
        String plane, SymbolicRouteNetwork<R> network, Predicate<SymbolicRoute<R>> eligible) {
      _plane = plane;
      _network = network;
      _eligible = eligible;
    }

    @Override
    public void collect(Map<SourceKey, DesiredMainRoute> desired) {
      for (GuardedRib<R> rib : _network.getRibs().values()) {
        for (GuardedRibEntry<R> candidate : rib.getEntries()) {
          for (Map.Entry<SymbolicRouteContributionId, GuardedRibEntry<R>> contribution :
              rib.getContributionEntries(candidate.getSymbolicRoute().getKey()).entrySet()) {
            GuardedRibEntry<R> entry = contribution.getValue();
            SymbolicRoute<R> symbolic = entry.getSymbolicRoute();
            if (!_eligible.test(symbolic)
                || symbolic.getRoute().getAbstractRoute().getNonRouting()
                || !entry.getSelectionGuard().isSatisfiable()) {
              continue;
            }
            desired.put(
                new SourceKey(_plane, symbolic.getKey(), contribution.getKey()),
                new DesiredMainRoute(
                    new AnnotatedRoute<>(
                        symbolic.getRoute().getAbstractRoute(), symbolic.getKey().getVrf()),
                    entry.getSelectionGuard(),
                    symbolic.getProvenance()));
          }
        }
      }
    }
  }

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _mainNetwork;
  @Nonnull private final List<Source> _sources;
  @Nonnull private final Set<String> _planes;
  @Nonnull private final Map<SourceKey, String> _messageIds;
  @Nonnull private final Map<SourceKey, ActiveMainRoute> _active;
  @Nonnull private SymbolicRouteConvergenceResult _lastConvergence;

  public BatfishMainRibReconciler(SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork) {
    _mainNetwork = requireNonNull(mainNetwork, "mainNetwork must be provided");
    _sources = new ArrayList<>();
    _planes = new LinkedHashSet<>();
    _messageIds = new LinkedHashMap<>();
    _active = new LinkedHashMap<>();
    _lastConvergence = new SymbolicRouteConvergenceResult(0, 0, 0);
  }

  /** Adds one protocol plane, registers its stable-state callback, and reconciles current state. */
  public <R extends AbstractRouteDecorator> void registerSource(
      String plane, SymbolicRouteNetwork<R> network, Predicate<SymbolicRoute<R>> eligible) {
    String checkedPlane = requireNonNull(plane, "plane must be provided");
    SymbolicRouteNetwork<R> checkedNetwork = requireNonNull(network, "network must be provided");
    if (!_planes.add(checkedPlane)) {
      throw new IllegalArgumentException("MAIN source plane is already registered");
    }
    _sources.add(
        new TypedSource<>(
            checkedPlane, checkedNetwork, requireNonNull(eligible, "eligible must be provided")));
    checkedNetwork.getEngine().addStableStateListener(this::reconcile);
    reconcile();
  }

  /** Applies a semantic diff from every registered protocol plane to MAIN. */
  @Nonnull
  public SymbolicRouteConvergenceResult reconcile() {
    Map<SourceKey, DesiredMainRoute> desired = new LinkedHashMap<>();
    _sources.forEach(source -> source.collect(desired));
    List<SymbolicRouteContributionId> withdrawals = new ArrayList<>();
    for (Map.Entry<SourceKey, ActiveMainRoute> active : _active.entrySet()) {
      DesiredMainRoute next = desired.get(active.getKey());
      if (next == null || !active.getValue()._route.equals(next._route)) {
        withdrawals.add(active.getValue()._contributionId);
      }
    }
    SymbolicRouteConvergenceResult withdrawalResult =
        withdrawals.isEmpty()
            ? new SymbolicRouteConvergenceResult(0, 0, 0)
            : _mainNetwork.getEngine().withdraw(withdrawals);

    List<SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>>> advertisements = new ArrayList<>();
    Map<SourceKey, ActiveMainRoute> nextActive = new LinkedHashMap<>();
    for (Map.Entry<SourceKey, DesiredMainRoute> desiredEntry : desired.entrySet()) {
      SourceKey sourceKey = desiredEntry.getKey();
      DesiredMainRoute next = desiredEntry.getValue();
      ActiveMainRoute previous = _active.get(sourceKey);
      String messageId =
          _messageIds.computeIfAbsent(
              sourceKey, unused -> "protocol-to-main-" + _messageIds.size());
      String router = sourceKey._routeKey.getRouter();
      SymbolicRouteContributionId contributionId =
          new SymbolicRouteContributionId(messageId, router, router);
      if (previous == null
          || !previous._route.equals(next._route)
          || !previous._guard.isEquivalentTo(next._guard)) {
        advertisements.add(
            new SymbolicRouteMessage<>(
                messageId,
                router,
                router,
                SymbolicRouteMessage.Stage.INGRESS,
                next._route,
                next._guard,
                next._provenance));
      }
      nextActive.put(sourceKey, new ActiveMainRoute(contributionId, next._route, next._guard));
    }
    SymbolicRouteConvergenceResult advertisementResult =
        advertisements.isEmpty()
            ? new SymbolicRouteConvergenceResult(0, 0, 0)
            : _mainNetwork.getEngine().converge(advertisements);
    _active.clear();
    _active.putAll(nextActive);
    _lastConvergence =
        new SymbolicRouteConvergenceResult(
            withdrawalResult.getProcessedMessages() + advertisementResult.getProcessedMessages(),
            withdrawalResult.getProcessedWithdrawals()
                + advertisementResult.getProcessedWithdrawals(),
            withdrawalResult.getRibUpdates() + advertisementResult.getRibUpdates());
    return _lastConvergence;
  }

  public int getActiveContributionCount() {
    return _active.size();
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getLastConvergence() {
    return _lastConvergence;
  }
}
