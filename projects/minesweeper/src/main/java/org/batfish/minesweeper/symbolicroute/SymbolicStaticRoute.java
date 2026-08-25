package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.StaticRoute;

/** A strongly typed configured static route awaiting Batfish-backed next-hop activation. */
public final class SymbolicStaticRoute {

  @Nonnull private final String _messageId;
  @Nonnull private final String _router;
  @Nonnull private final AnnotatedRoute<StaticRoute> _route;
  @Nonnull private final RouteGuard _configurationGuard;

  public SymbolicStaticRoute(
      String messageId,
      String router,
      AnnotatedRoute<StaticRoute> route,
      RouteGuard configurationGuard) {
    _messageId = requireNonNull(messageId, "messageId must be provided");
    _router = requireNonNull(router, "router must be provided");
    _route = requireNonNull(route, "route must be provided");
    _configurationGuard = requireNonNull(configurationGuard, "configurationGuard must be provided");
  }

  @Nonnull
  public String getMessageId() {
    return _messageId;
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public AnnotatedRoute<StaticRoute> getRoute() {
    return _route;
  }

  @Nonnull
  public RouteGuard getConfigurationGuard() {
    return _configurationGuard;
  }
}
