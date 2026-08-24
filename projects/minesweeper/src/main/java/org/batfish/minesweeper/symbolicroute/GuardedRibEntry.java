package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A guarded RIB candidate and its dynamically derived selection guard. */
public final class GuardedRibEntry<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRoute<R> _symbolicRoute;
  @Nonnull private final RouteGuard _selectionGuard;

  GuardedRibEntry(SymbolicRoute<R> symbolicRoute, RouteGuard selectionGuard) {
    _symbolicRoute = requireNonNull(symbolicRoute, "symbolicRoute must be provided");
    _selectionGuard = requireNonNull(selectionGuard, "selectionGuard must be provided");
  }

  @Nonnull
  public SymbolicRoute<R> getSymbolicRoute() {
    return _symbolicRoute;
  }

  @Nonnull
  public RouteGuard getAvailabilityGuard() {
    return _symbolicRoute.getAvailabilityGuard();
  }

  @Nonnull
  public RouteGuard getSelectionGuard() {
    return _selectionGuard;
  }
}
