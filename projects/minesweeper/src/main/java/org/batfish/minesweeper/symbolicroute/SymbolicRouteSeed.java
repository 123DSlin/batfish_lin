package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A locally originated route advertisement used to initialize symbolic convergence. */
public final class SymbolicRouteSeed<R extends AbstractRouteDecorator> {

  @Nonnull private final String _messageId;
  @Nonnull private final String _originRouter;
  @Nonnull private final R _route;
  @Nonnull private final RouteGuard _guard;
  @Nullable private final LinkFailureKey _linkFailureKey;

  public SymbolicRouteSeed(String messageId, String originRouter, R route, RouteGuard guard) {
    this(messageId, originRouter, route, guard, null);
  }

  public SymbolicRouteSeed(
      String messageId,
      String originRouter,
      R route,
      RouteGuard guard,
      @Nullable LinkFailureKey linkFailureKey) {
    _messageId = requireNonNull(messageId, "messageId must be provided");
    _originRouter = requireNonNull(originRouter, "originRouter must be provided");
    _route = requireNonNull(route, "route must be provided");
    _guard = requireNonNull(guard, "guard must be provided");
    _linkFailureKey = linkFailureKey;
    if (_linkFailureKey != null && !_linkFailureKey.containsRouter(_originRouter)) {
      throw new IllegalArgumentException("connected seed link must contain its origin router");
    }
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

  @Nullable
  public LinkFailureKey getLinkFailureKey() {
    return _linkFailureKey;
  }
}
