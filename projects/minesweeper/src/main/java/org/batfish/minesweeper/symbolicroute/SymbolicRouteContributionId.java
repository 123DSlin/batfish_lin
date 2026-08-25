package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;

/** Identity of one directed route-advertisement contribution to a candidate. */
public final class SymbolicRouteContributionId {
  @Nonnull private final String _messageId;
  @Nonnull private final String _sender;
  @Nonnull private final String _receiver;

  public SymbolicRouteContributionId(String messageId, String sender, String receiver) {
    _messageId = requireNonNull(messageId, "messageId must be provided");
    _sender = requireNonNull(sender, "sender must be provided");
    _receiver = requireNonNull(receiver, "receiver must be provided");
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

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof SymbolicRouteContributionId)) return false;
    SymbolicRouteContributionId that = (SymbolicRouteContributionId) o;
    return _messageId.equals(that._messageId)
        && _sender.equals(that._sender)
        && _receiver.equals(that._receiver);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_messageId, _sender, _receiver);
  }
}
