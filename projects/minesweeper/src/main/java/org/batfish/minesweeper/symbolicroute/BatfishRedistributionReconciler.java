package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;

/** Applies Batfish policy outcomes using advertise, withdraw, and atomic route replacement. */
public final class BatfishRedistributionReconciler {

  private static final class Installed {
    @Nonnull private final SymbolicRouteContributionId _contributionId;
    @Nonnull private final AnnotatedRoute<AbstractRoute> _route;
    private final long _generation;

    private Installed(
        SymbolicRouteContributionId contributionId,
        AnnotatedRoute<AbstractRoute> route,
        long generation) {
      _contributionId = contributionId;
      _route = route;
      _generation = generation;
    }
  }

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _network;
  @Nonnull private final Map<BatfishRedistributionKey, Installed> _installed;

  public BatfishRedistributionReconciler(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network) {
    _network = requireNonNull(network, "network must be provided");
    _installed = new LinkedHashMap<>();
  }

  /** Reconciles one deterministic policy result with the target symbolic RIB. */
  @Nonnull
  public <R extends AbstractRoute> SymbolicRouteConvergenceResult reconcile(
      BatfishRedistributionKey key, BatfishRoutingPolicyResult<R> policyResult, RouteGuard guard) {
    requireNonNull(key, "key must be provided");
    requireNonNull(policyResult, "policyResult must be provided");
    requireNonNull(guard, "guard must be provided");
    _network.getRib(key.getRouter());
    Installed old = _installed.get(key);
    if (policyResult.getOutcome() != BatfishRoutingPolicyResult.Outcome.ACCEPTED) {
      if (old == null) {
        return new SymbolicRouteConvergenceResult(0, 0, 0);
      }
      _installed.remove(key);
      return _network.getEngine().withdraw(ImmutableList.of(old._contributionId));
    }
    AnnotatedRoute<AbstractRoute> route = widen(policyResult.getOutputRoute().get());
    validateOutput(key, route);
    if (old == null) {
      Installed added = installed(key, route, 0L);
      SymbolicRouteConvergenceResult result =
          _network.getEngine().converge(ImmutableList.of(message(key, added, guard)));
      _installed.put(key, added);
      return result;
    }
    if (old._route.equals(route)) {
      return _network.getEngine().converge(ImmutableList.of(message(key, old, guard)));
    }
    Installed replacement = installed(key, route, old._generation + 1L);
    SymbolicRouteConvergenceResult result =
        _network.getEngine().replace(old._contributionId, message(key, replacement, guard));
    _installed.put(key, replacement);
    return result;
  }

  @Nonnull
  public Optional<SymbolicRouteContributionId> getInstalledContributionId(
      BatfishRedistributionKey key) {
    Installed installed = _installed.get(requireNonNull(key, "key must be provided"));
    return installed == null ? Optional.empty() : Optional.of(installed._contributionId);
  }

  private static Installed installed(
      BatfishRedistributionKey key, AnnotatedRoute<AbstractRoute> route, long generation) {
    String messageId = key.messageNamespace() + ":generation:" + generation;
    return new Installed(
        new SymbolicRouteContributionId(messageId, key.getRouter(), key.getRouter()),
        route,
        generation);
  }

  private static SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>> message(
      BatfishRedistributionKey key, Installed installed, RouteGuard guard) {
    return new SymbolicRouteSeed<>(
            installed._contributionId.getMessageId(), key.getRouter(), installed._route, guard)
        .toMessage();
  }

  private static void validateOutput(
      BatfishRedistributionKey key, AnnotatedRoute<AbstractRoute> route) {
    if (!route.getSourceVrf().equals(key.getTargetVrf())) {
      throw new IllegalArgumentException("policy output VRF does not match redistribution target");
    }
    if (route.getAbstractRoute().getProtocol() != key.getTargetProtocol()) {
      throw new IllegalArgumentException(
          "policy output protocol does not match redistribution target");
    }
  }

  private static <R extends AbstractRoute> AnnotatedRoute<AbstractRoute> widen(
      AnnotatedRoute<R> route) {
    return new AnnotatedRoute<>(route.getRoute(), route.getSourceVrf());
  }
}
