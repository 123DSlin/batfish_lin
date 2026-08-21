package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;

/** Protocol-independent identity of a route candidate in a device RIB. */
public final class SymbolicRouteKey {

  @Nonnull private final String _router;
  @Nonnull private final RoutingProtocol _protocol;
  @Nonnull private final Prefix _network;
  @Nonnull private final String _sourceId;
  @Nonnull private final String _attributeFingerprint;

  public SymbolicRouteKey(
      String router,
      RoutingProtocol protocol,
      Prefix network,
      String sourceId,
      String attributeFingerprint) {
    _router = requireNonNull(router, "router must be provided");
    _protocol = requireNonNull(protocol, "protocol must be provided");
    _network = requireNonNull(network, "network must be provided");
    _sourceId = requireNonNull(sourceId, "sourceId must be provided");
    _attributeFingerprint =
        requireNonNull(attributeFingerprint, "attributeFingerprint must be provided");
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public RoutingProtocol getProtocol() {
    return _protocol;
  }

  @Nonnull
  public Prefix getNetwork() {
    return _network;
  }

  @Nonnull
  public String getSourceId() {
    return _sourceId;
  }

  @Nonnull
  public String getAttributeFingerprint() {
    return _attributeFingerprint;
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
    return _router.equals(that._router)
        && _protocol == that._protocol
        && _network.equals(that._network)
        && _sourceId.equals(that._sourceId)
        && _attributeFingerprint.equals(that._attributeFingerprint);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_router, _protocol, _network, _sourceId, _attributeFingerprint);
  }

  @Override
  public String toString() {
    return String.format(
        "%s:%s:%s:%s:%s", _router, _protocol, _network, _sourceId, _attributeFingerprint);
  }
}
