package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.isis.IsisEdge;

/** Parsed Batfish IS-IS circuit and its directed symbolic-session identity. */
public final class BatfishIsisEdge {

  @Nonnull private final String _sessionId;
  @Nonnull private final IsisEdge _edge;
  @Nonnull private final Configuration _senderConfiguration;
  @Nonnull private final Configuration _receiverConfiguration;
  @Nonnull private final Interface _senderInterface;
  @Nonnull private final Interface _receiverInterface;

  public BatfishIsisEdge(
      String sessionId,
      IsisEdge edge,
      Configuration senderConfiguration,
      Configuration receiverConfiguration,
      Interface senderInterface,
      Interface receiverInterface) {
    _sessionId = requireNonNull(sessionId, "sessionId must be provided");
    _edge = requireNonNull(edge, "edge must be provided");
    _senderConfiguration =
        requireNonNull(senderConfiguration, "senderConfiguration must be provided");
    _receiverConfiguration =
        requireNonNull(receiverConfiguration, "receiverConfiguration must be provided");
    _senderInterface = requireNonNull(senderInterface, "senderInterface must be provided");
    _receiverInterface = requireNonNull(receiverInterface, "receiverInterface must be provided");
    if (!_edge.getNode1().getNode().equals(_senderConfiguration.getHostname())
        || !_edge.getNode1().getInterfaceName().equals(_senderInterface.getName())
        || !_edge.getNode2().getNode().equals(_receiverConfiguration.getHostname())
        || !_edge.getNode2().getInterfaceName().equals(_receiverInterface.getName())) {
      throw new IllegalArgumentException("IS-IS edge endpoints must match Batfish objects");
    }
  }

  @Nonnull
  public String getSessionId() {
    return _sessionId;
  }

  @Nonnull
  public IsisEdge getEdge() {
    return _edge;
  }

  @Nonnull
  public Configuration getSenderConfiguration() {
    return _senderConfiguration;
  }

  @Nonnull
  public Configuration getReceiverConfiguration() {
    return _receiverConfiguration;
  }

  @Nonnull
  public Interface getSenderInterface() {
    return _senderInterface;
  }

  @Nonnull
  public Interface getReceiverInterface() {
    return _receiverInterface;
  }
}
