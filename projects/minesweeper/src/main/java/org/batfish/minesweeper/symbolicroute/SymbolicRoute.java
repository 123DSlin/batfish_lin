package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A concrete protocol route paired with the condition under which it is present in a RIB. */
public final class SymbolicRoute<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRouteKey _key;
  @Nonnull private final R _route;
  @Nonnull private final RouteGuard _presenceGuard;
  @Nonnull private final SymbolicRouteProvenance _provenance;

  public SymbolicRoute(
      SymbolicRouteKey key, R route, RouteGuard presenceGuard, SymbolicRouteProvenance provenance) {
    _key = requireNonNull(key, "key must be provided");
    _route = requireNonNull(route, "route must be provided");
    _presenceGuard = requireNonNull(presenceGuard, "presenceGuard must be provided");
    _provenance = requireNonNull(provenance, "provenance must be provided");
  }

  @Nonnull
  public SymbolicRouteKey getKey() {
    return _key;
  }

  @Nonnull
  public R getRoute() {
    return _route;
  }

  @Nonnull
  public RouteGuard getPresenceGuard() {
    return _presenceGuard;
  }

  @Nonnull
  public SymbolicRouteProvenance getProvenance() {
    return _provenance;
  }

  public SymbolicRoute<R> withPresenceGuard(RouteGuard presenceGuard) {
    return new SymbolicRoute<>(_key, _route, presenceGuard, _provenance);
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicRoute)) {
      return false;
    }
    SymbolicRoute<?> that = (SymbolicRoute<?>) o;
    return _key.equals(that._key)
        && _route.equals(that._route)
        && _presenceGuard.equals(that._presenceGuard)
        && _provenance.equals(that._provenance);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_key, _route, _presenceGuard, _provenance);
  }
}
