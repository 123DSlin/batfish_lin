package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.RoutingProtocol.ISIS_L2;
import static org.batfish.dataplane.protocols.IsisProtocolHelper.convertRouteLevel1ToLevel2;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Vrf;

/** Maintains guarded L2 contributions derived from the stable selected state of the L1 RIBs. */
public final class BatfishIsisLevelTransitionReconciler {

  private static final class TransitionKey {
    @Nonnull private final SymbolicRouteKey _routeKey;
    @Nonnull private final SymbolicRouteContributionId _sourceContributionId;

    private TransitionKey(
        SymbolicRouteKey routeKey, SymbolicRouteContributionId sourceContributionId) {
      _routeKey = routeKey;
      _sourceContributionId = sourceContributionId;
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof TransitionKey)) {
        return false;
      }
      TransitionKey that = (TransitionKey) object;
      return _routeKey.equals(that._routeKey)
          && _sourceContributionId.equals(that._sourceContributionId);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_routeKey, _sourceContributionId);
    }
  }

  private static final class DesiredTransition {
    @Nonnull private final AnnotatedRoute<IsisRoute> _route;
    @Nonnull private final RouteGuard _guard;
    @Nonnull private final SymbolicRouteProvenance _provenance;

    private DesiredTransition(
        AnnotatedRoute<IsisRoute> route, RouteGuard guard, SymbolicRouteProvenance provenance) {
      _route = route;
      _guard = guard;
      _provenance = provenance;
    }
  }

  private static final class ActiveTransition {
    @Nonnull private final SymbolicRouteContributionId _contributionId;
    @Nonnull private final AnnotatedRoute<IsisRoute> _route;
    @Nonnull private final RouteGuard _guard;

    private ActiveTransition(
        SymbolicRouteContributionId contributionId,
        AnnotatedRoute<IsisRoute> route,
        RouteGuard guard) {
      _contributionId = contributionId;
      _route = route;
      _guard = guard;
    }
  }

  @Nonnull private final Map<String, Configuration> _configurations;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l1Network;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l2Network;
  @Nonnull private final Map<TransitionKey, String> _messageIds;
  @Nonnull private final Map<TransitionKey, ActiveTransition> _active;
  @Nonnull private SymbolicRouteConvergenceResult _lastConvergence;

  public BatfishIsisLevelTransitionReconciler(
      Map<String, Configuration> configurations,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l1Network,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l2Network) {
    _configurations = requireNonNull(configurations, "configurations must be provided");
    _l1Network = requireNonNull(l1Network, "l1Network must be provided");
    _l2Network = requireNonNull(l2Network, "l2Network must be provided");
    _messageIds = new LinkedHashMap<>();
    _active = new LinkedHashMap<>();
    _lastConvergence = new SymbolicRouteConvergenceResult(0, 0, 0);
  }

  /** Reconciles all cross-level contributions and fully drains resulting L2 propagation. */
  @Nonnull
  public SymbolicRouteConvergenceResult reconcile() {
    Map<TransitionKey, DesiredTransition> desired = computeDesiredTransitions();
    List<SymbolicRouteContributionId> withdrawals = new ArrayList<>();
    for (Map.Entry<TransitionKey, ActiveTransition> active : _active.entrySet()) {
      DesiredTransition next = desired.get(active.getKey());
      if (next == null || !active.getValue()._route.equals(next._route)) {
        withdrawals.add(active.getValue()._contributionId);
      }
    }
    SymbolicRouteConvergenceResult withdrawalResult =
        withdrawals.isEmpty()
            ? new SymbolicRouteConvergenceResult(0, 0, 0)
            : _l2Network.getEngine().withdraw(withdrawals);

    List<SymbolicRouteMessage<AnnotatedRoute<IsisRoute>>> advertisements = new ArrayList<>();
    Map<TransitionKey, ActiveTransition> nextActive = new LinkedHashMap<>();
    for (Map.Entry<TransitionKey, DesiredTransition> desiredEntry : desired.entrySet()) {
      TransitionKey sourceKey = desiredEntry.getKey();
      DesiredTransition next = desiredEntry.getValue();
      ActiveTransition previous = _active.get(sourceKey);
      String messageId =
          _messageIds.computeIfAbsent(
              sourceKey, unused -> "isis-level-transition-" + _messageIds.size());
      SymbolicRouteContributionId contributionId =
          new SymbolicRouteContributionId(
              messageId, sourceKey._routeKey.getRouter(), sourceKey._routeKey.getRouter());
      if (previous == null
          || !previous._route.equals(next._route)
          || !previous._guard.isEquivalentTo(next._guard)) {
        advertisements.add(
            new SymbolicRouteMessage<>(
                messageId,
                sourceKey._routeKey.getRouter(),
                sourceKey._routeKey.getRouter(),
                SymbolicRouteMessage.Stage.INGRESS,
                next._route,
                next._guard,
                next._provenance));
      }
      nextActive.put(sourceKey, new ActiveTransition(contributionId, next._route, next._guard));
    }
    _active.clear();
    _active.putAll(nextActive);
    SymbolicRouteConvergenceResult advertisementResult =
        advertisements.isEmpty()
            ? new SymbolicRouteConvergenceResult(0, 0, 0)
            : _l2Network.getEngine().converge(advertisements);
    _lastConvergence =
        new SymbolicRouteConvergenceResult(
            withdrawalResult.getProcessedMessages() + advertisementResult.getProcessedMessages(),
            withdrawalResult.getProcessedWithdrawals()
                + advertisementResult.getProcessedWithdrawals(),
            withdrawalResult.getRibUpdates() + advertisementResult.getRibUpdates());
    return _lastConvergence;
  }

  public int getActiveTransitionCount() {
    return _active.size();
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getLastConvergence() {
    return _lastConvergence;
  }

  @Nonnull
  private Map<TransitionKey, DesiredTransition> computeDesiredTransitions() {
    Map<TransitionKey, DesiredTransition> desired = new LinkedHashMap<>();
    for (Map.Entry<String, GuardedRib<AnnotatedRoute<IsisRoute>>> routerRib :
        _l1Network.getRibs().entrySet()) {
      Configuration configuration = _configurations.get(routerRib.getKey());
      GuardedRib<AnnotatedRoute<IsisRoute>> rib = routerRib.getValue();
      for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> candidate : rib.getEntries()) {
        for (Map.Entry<SymbolicRouteContributionId, GuardedRibEntry<AnnotatedRoute<IsisRoute>>>
            contribution :
                rib.getContributionEntries(candidate.getSymbolicRoute().getKey()).entrySet()) {
          GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry = contribution.getValue();
          SymbolicRoute<AnnotatedRoute<IsisRoute>> symbolic = entry.getSymbolicRoute();
          AnnotatedRoute<IsisRoute> annotated = symbolic.getRoute();
          Vrf vrf = configuration.getVrfs().get(annotated.getSourceVrf());
          if (!isTransitionRouter(vrf) || !entry.getSelectionGuard().isSatisfiable()) {
            continue;
          }
          int l2Admin =
              ISIS_L2.getDefaultAdministrativeCost(configuration.getConfigurationFormat());
          Optional<IsisRoute> upgraded =
              convertRouteLevel1ToLevel2(annotated.getRoute(), ISIS_L2, l2Admin);
          if (!upgraded.isPresent()) {
            continue;
          }
          desired.put(
              new TransitionKey(symbolic.getKey(), contribution.getKey()),
              new DesiredTransition(
                  new AnnotatedRoute<>(upgraded.get(), annotated.getSourceVrf()),
                  entry.getSelectionGuard(),
                  symbolic.getProvenance()));
        }
      }
    }
    return desired;
  }

  private static boolean isTransitionRouter(Vrf vrf) {
    return vrf != null
        && vrf.getIsisProcess() != null
        && vrf.getIsisProcess().getLevel1() != null
        && vrf.getIsisProcess().getLevel2() != null
        && !vrf.getIsisProcess().getOverload();
  }
}
