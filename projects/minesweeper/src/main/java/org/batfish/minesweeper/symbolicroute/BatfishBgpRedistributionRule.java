package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.RoutingProtocol;

/** One configured main-RIB-to-BGP redistribution boundary in a router VRF. */
public final class BatfishBgpRedistributionRule {

  @Nonnull private final String _ruleId;
  @Nonnull private final String _router;
  @Nonnull private final String _sourceVrf;
  @Nonnull private final String _targetVrf;
  @Nonnull private final String _policyName;
  @Nonnull private final RoutingProtocol _targetProtocol;

  public BatfishBgpRedistributionRule(
      String ruleId,
      String router,
      String sourceVrf,
      String targetVrf,
      String policyName,
      RoutingProtocol targetProtocol) {
    _ruleId = requireNonNull(ruleId, "ruleId must be provided");
    _router = requireNonNull(router, "router must be provided");
    _sourceVrf = requireNonNull(sourceVrf, "sourceVrf must be provided");
    _targetVrf = requireNonNull(targetVrf, "targetVrf must be provided");
    _policyName = requireNonNull(policyName, "policyName must be provided");
    _targetProtocol = requireNonNull(targetProtocol, "targetProtocol must be provided");
    if (_targetProtocol != RoutingProtocol.BGP && _targetProtocol != RoutingProtocol.IBGP) {
      throw new IllegalArgumentException("redistribution target must be BGP or IBGP");
    }
  }

  @Nonnull
  public String getRuleId() {
    return _ruleId;
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public String getSourceVrf() {
    return _sourceVrf;
  }

  @Nonnull
  public String getTargetVrf() {
    return _targetVrf;
  }

  @Nonnull
  public String getPolicyName() {
    return _policyName;
  }

  @Nonnull
  public RoutingProtocol getTargetProtocol() {
    return _targetProtocol;
  }
}
