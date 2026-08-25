package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;

/** One directed protocol adjacency and the condition under which its link is available. */
public final class SymbolicRouteSession {

  @Nonnull private final String _sessionId;
  @Nonnull private final String _sender;
  @Nonnull private final String _receiver;
  @Nonnull private final RouteGuard _linkGuard;

  public SymbolicRouteSession(String sender, String receiver, RouteGuard linkGuard) {
    this(sender + "->" + receiver, sender, receiver, linkGuard);
  }

  public SymbolicRouteSession(
      String sessionId, String sender, String receiver, RouteGuard linkGuard) {
    _sessionId = requireNonNull(sessionId, "sessionId must be provided");
    _sender = requireNonNull(sender, "sender must be provided");
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _linkGuard = requireNonNull(linkGuard, "linkGuard must be provided");
    if (_sender.equals(_receiver)) {
      throw new IllegalArgumentException("a symbolic route session must connect two routers");
    }
  }

  @Nonnull
  public String getSessionId() {
    return _sessionId;
  }

  @Nonnull
  public String getSender() {
    return _sender;
  }

  @Nonnull
  public String getReceiver() {
    return _receiver;
  }

  @Nonnull
  public RouteGuard getLinkGuard() {
    return _linkGuard;
  }
}
