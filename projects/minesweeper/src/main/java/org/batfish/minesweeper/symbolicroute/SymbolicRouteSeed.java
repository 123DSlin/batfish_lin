package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A locally originated route advertisement used to initialize symbolic convergence. */
public final class SymbolicRouteSeed<R extends AbstractRouteDecorator> {

  @Nonnull private final String _messageId;
  @Nonnull private final String _originRouter;
  @Nonnull private final R _route;
  @Nonnull private final RouteGuard _guard;

  public SymbolicRouteSeed(String messageId, String originRouter, R route, RouteGuard guard) {
    _messageId = requireNonNull(messageId, "messageId must be provided");
    _originRouter = requireNonNull(originRouter, "originRouter must be provided");
    _route = requireNonNull(route, "route must be provided");
    _guard = requireNonNull(guard, "guard must be provided");
  }

  @Nonnull
  SymbolicRouteMessage<R> toMessage() {
    return new SymbolicRouteMessage<>(
        _messageId,
        _originRouter,
        _originRouter,
        SymbolicRouteMessage.Stage.INGRESS,
        _route,
        _guard,
        new SymbolicRouteProvenance(
            _originRouter, _originRouter, null, null, ImmutableList.of(_originRouter), null));
  }

  @Nonnull
  public String getMessageId() {
    return _messageId;
  }

  @Nonnull
  public String getOriginRouter() {
    return _originRouter;
  }
}
