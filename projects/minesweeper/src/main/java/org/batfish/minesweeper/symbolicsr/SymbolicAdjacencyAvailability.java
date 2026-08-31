package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Canonical failure identity and up-guard for one directed adjacency endpoint. */
public final class SymbolicAdjacencyAvailability {
  private final LinkFailureKey _failureKey;
  private final RouteGuard _guard;
  private final SymbolicAdjacencyEndpoint _target;

  public SymbolicAdjacencyAvailability(
      LinkFailureKey failureKey, RouteGuard guard, SymbolicAdjacencyEndpoint target) {
    _failureKey = requireNonNull(failureKey, "failure key must be provided");
    _guard = requireNonNull(guard, "guard must be provided");
    _target = requireNonNull(target, "target must be provided");
  }

  public LinkFailureKey getFailureKey() {
    return _failureKey;
  }

  public RouteGuard getGuard() {
    return _guard;
  }

  public SymbolicAdjacencyEndpoint getTarget() {
    return _target;
  }
}
