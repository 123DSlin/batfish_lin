package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;

/** Stable identity of one concrete route candidate in a scoped device RIB. */
public final class SymbolicRouteKey {

  @Nonnull private final String _router;
  @Nonnull private final String _vrf;
  @Nonnull private final AbstractRouteDecorator _route;

  public SymbolicRouteKey(String router, String vrf, AbstractRouteDecorator route) {
    _router = requireNonNull(router, "router must be provided");
    _vrf = requireNonNull(vrf, "vrf must be provided");
    _route = requireNonNull(route, "route must be provided");
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public String getVrf() {
    return _vrf;
  }

  @Nonnull
  public RoutingProtocol getProtocol() {
    return _route.getAbstractRoute().getProtocol();
  }

  @Nonnull
  public Prefix getNetwork() {
    return _route.getNetwork();
  }

  @Nonnull
  public AbstractRouteDecorator getRoute() {
    return _route;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicRouteKey)) {
      return false;
    }
    SymbolicRouteKey that = (SymbolicRouteKey) o;
    return _router.equals(that._router) && _vrf.equals(that._vrf) && _route.equals(that._route);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_router, _vrf, _route);
  }

  @Override
  public String toString() {
    return String.format("%s:%s:%s:%s", _router, _vrf, getProtocol(), getNetwork());
  }
}
