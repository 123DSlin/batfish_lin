package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.BgpPeerConfig;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.BgpSessionProperties;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Ip;

/** Batfish objects required to evaluate one directed IPv4-unicast BGP edge. */
public final class BatfishBgpEdge {

  @Nonnull private final String _sessionId;
  @Nonnull private final String _senderVrf;
  @Nonnull private final String _receiverVrf;
  @Nonnull private final Configuration _senderConfiguration;
  @Nonnull private final Configuration _receiverConfiguration;
  @Nonnull private final BgpPeerConfig _senderPeer;
  @Nonnull private final BgpPeerConfig _receiverPeer;
  @Nonnull private final BgpProcess _senderProcess;
  @Nonnull private final BgpProcess _receiverProcess;
  @Nonnull private final BgpSessionProperties _exportSessionProperties;
  @Nonnull private final BgpSessionProperties _importSessionProperties;
  @Nonnull private final Ip _receiverPeerIp;
  @Nullable private final String _receiverPeerInterface;
  private final boolean _allowLocalAsIn;

  public BatfishBgpEdge(
      String sessionId,
      String senderVrf,
      String receiverVrf,
      Configuration senderConfiguration,
      Configuration receiverConfiguration,
      BgpPeerConfig senderPeer,
      BgpPeerConfig receiverPeer,
      BgpProcess senderProcess,
      BgpProcess receiverProcess,
      BgpSessionProperties exportSessionProperties,
      BgpSessionProperties importSessionProperties,
      Ip receiverPeerIp,
      @Nullable String receiverPeerInterface,
      boolean allowLocalAsIn) {
    _sessionId = requireNonNull(sessionId, "sessionId must be provided");
    _senderVrf = requireNonNull(senderVrf, "senderVrf must be provided");
    _receiverVrf = requireNonNull(receiverVrf, "receiverVrf must be provided");
    _senderConfiguration =
        requireNonNull(senderConfiguration, "senderConfiguration must be provided");
    _receiverConfiguration =
        requireNonNull(receiverConfiguration, "receiverConfiguration must be provided");
    _senderPeer = requireNonNull(senderPeer, "senderPeer must be provided");
    _receiverPeer = requireNonNull(receiverPeer, "receiverPeer must be provided");
    _senderProcess = requireNonNull(senderProcess, "senderProcess must be provided");
    _receiverProcess = requireNonNull(receiverProcess, "receiverProcess must be provided");
    _exportSessionProperties =
        requireNonNull(exportSessionProperties, "exportSessionProperties must be provided");
    _importSessionProperties =
        requireNonNull(importSessionProperties, "importSessionProperties must be provided");
    _receiverPeerIp = requireNonNull(receiverPeerIp, "receiverPeerIp must be provided");
    _receiverPeerInterface = receiverPeerInterface;
    _allowLocalAsIn = allowLocalAsIn;
  }

  @Nonnull
  public String getSessionId() {
    return _sessionId;
  }

  @Nonnull
  public String getSenderVrf() {
    return _senderVrf;
  }

  @Nonnull
  public String getReceiverVrf() {
    return _receiverVrf;
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
  public BgpPeerConfig getSenderPeer() {
    return _senderPeer;
  }

  @Nonnull
  public BgpPeerConfig getReceiverPeer() {
    return _receiverPeer;
  }

  @Nonnull
  public BgpProcess getSenderProcess() {
    return _senderProcess;
  }

  @Nonnull
  public BgpProcess getReceiverProcess() {
    return _receiverProcess;
  }

  @Nonnull
  public BgpSessionProperties getExportSessionProperties() {
    return _exportSessionProperties;
  }

  @Nonnull
  public BgpSessionProperties getImportSessionProperties() {
    return _importSessionProperties;
  }

  @Nonnull
  public Ip getReceiverPeerIp() {
    return _receiverPeerIp;
  }

  @Nullable
  public String getReceiverPeerInterface() {
    return _receiverPeerInterface;
  }

  public boolean getAllowLocalAsIn() {
    return _allowLocalAsIn;
  }
}
