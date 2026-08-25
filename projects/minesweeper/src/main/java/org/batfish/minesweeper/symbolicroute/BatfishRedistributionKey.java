package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;
import org.batfish.datamodel.RoutingProtocol;

/** Stable identity of one policy-controlled redistribution relationship. */
public final class BatfishRedistributionKey {

  @Nonnull private final String _sourceMessageId;
  @Nonnull private final String _router;
  @Nonnull private final String _sourceVrf;
  @Nonnull private final String _targetVrf;
  @Nonnull private final RoutingProtocol _sourceProtocol;
  @Nonnull private final RoutingProtocol _targetProtocol;
  @Nonnull private final String _policyName;

  public BatfishRedistributionKey(
      String sourceMessageId,
      String router,
      String sourceVrf,
      String targetVrf,
      RoutingProtocol sourceProtocol,
      RoutingProtocol targetProtocol,
      String policyName) {
    _sourceMessageId = requireNonNull(sourceMessageId, "sourceMessageId must be provided");
    _router = requireNonNull(router, "router must be provided");
    _sourceVrf = requireNonNull(sourceVrf, "sourceVrf must be provided");
    _targetVrf = requireNonNull(targetVrf, "targetVrf must be provided");
    _sourceProtocol = requireNonNull(sourceProtocol, "sourceProtocol must be provided");
    _targetProtocol = requireNonNull(targetProtocol, "targetProtocol must be provided");
    _policyName = requireNonNull(policyName, "policyName must be provided");
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public String getTargetVrf() {
    return _targetVrf;
  }

  @Nonnull
  public RoutingProtocol getTargetProtocol() {
    return _targetProtocol;
  }

  @Nonnull
  String messageNamespace() {
    return String.format(
        "redist:%d:%s:%d:%s:%d:%s:%s:%s:%s",
        _sourceVrf.length(),
        _sourceVrf,
        _targetVrf.length(),
        _targetVrf,
        _policyName.length(),
        _policyName,
        _sourceProtocol,
        _targetProtocol,
        _sourceMessageId);
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof BatfishRedistributionKey)) {
      return false;
    }
    BatfishRedistributionKey that = (BatfishRedistributionKey) o;
    return _sourceMessageId.equals(that._sourceMessageId)
        && _router.equals(that._router)
        && _sourceVrf.equals(that._sourceVrf)
        && _targetVrf.equals(that._targetVrf)
        && _sourceProtocol == that._sourceProtocol
        && _targetProtocol == that._targetProtocol
        && _policyName.equals(that._policyName);
  }

  @Override
  public int hashCode() {
    return Objects.hash(
        _sourceMessageId,
        _router,
        _sourceVrf,
        _targetVrf,
        _sourceProtocol,
        _targetProtocol,
        _policyName);
  }
}
