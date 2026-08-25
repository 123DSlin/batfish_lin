package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A guarded protocol message at an ingress or egress pipeline stage. */
public final class SymbolicRouteMessage<R extends AbstractRouteDecorator> {

  public enum Stage {
    EGRESS,
    INGRESS
  }

  @Nonnull private final String _messageId;
  @Nonnull private final String _sender;
  @Nonnull private final String _receiver;
  @Nullable private final String _sessionId;
  @Nonnull private final Stage _stage;
  @Nonnull private final R _route;
  @Nonnull private final RouteGuard _guard;
  @Nonnull private final SymbolicRouteProvenance _provenance;

  public SymbolicRouteMessage(
      String messageId,
      String sender,
      String receiver,
      Stage stage,
      R route,
      RouteGuard guard,
      SymbolicRouteProvenance provenance) {
    this(messageId, sender, receiver, null, stage, route, guard, provenance);
  }

  public SymbolicRouteMessage(
      String messageId,
      String sender,
      String receiver,
      @Nullable String sessionId,
      Stage stage,
      R route,
      RouteGuard guard,
      SymbolicRouteProvenance provenance) {
    _messageId = requireNonNull(messageId, "messageId must be provided");
    _sender = requireNonNull(sender, "sender must be provided");
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _sessionId = sessionId;
    _stage = requireNonNull(stage, "stage must be provided");
    _route = requireNonNull(route, "route must be provided");
    _guard = requireNonNull(guard, "guard must be provided");
    _provenance = requireNonNull(provenance, "provenance must be provided");
  }

  @Nonnull
  public String getMessageId() {
    return _messageId;
  }

  @Nonnull
  public String getSender() {
    return _sender;
  }

  @Nonnull
  public String getReceiver() {
    return _receiver;
  }

  /** Stable directed protocol-session identity, or null for a locally originated seed. */
  @Nullable
  public String getSessionId() {
    return _sessionId;
  }

  @Nonnull
  public Stage getStage() {
    return _stage;
  }

  @Nonnull
  public R getRoute() {
    return _route;
  }

  @Nonnull
  public RouteGuard getGuard() {
    return _guard;
  }

  @Nonnull
  public SymbolicRouteProvenance getProvenance() {
    return _provenance;
  }
}
