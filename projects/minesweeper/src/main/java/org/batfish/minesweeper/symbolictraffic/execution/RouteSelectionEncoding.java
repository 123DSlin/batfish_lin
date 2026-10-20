package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.List;
import org.batfish.datamodel.Ip;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/**
 * YU encoding of route selection {@code s_r} and (weighted) ECMP {@code c_r}.
 *
 * <p>The guarded control plane supplies {@code s_r}, preserving its complete concrete protocol
 * comparator. {@code s^{dstip}_r = 0} if {@code dstip} does not match {@code r}, and
 * {@code c^{dstip}_r = s_r / Σ_{r'} s_{r'}}.
 */
public final class RouteSelectionEncoding {

  private RouteSelectionEncoding() {}

  public static RouteGuard selection(ForwardingRule rule, List<ForwardingRule> rib, Ip dstIp) {
    if (!rule.matches(dstIp)) {
      return rule.getAvailability().and(rule.getAvailability().not());
    }
    return rule.getSelection();
  }

  public static SymbolicTrafficFraction ecmpRatio(
      ForwardingRule rule, List<ForwardingRule> rib, Ip dstIp) {
    SymbolicTrafficFraction numerator =
        SymbolicTrafficFraction.fromGuard(selection(rule, rib, dstIp));
    SymbolicTrafficFraction denominator = SymbolicTrafficFraction.zero();
    for (ForwardingRule other : rib) {
      denominator =
          denominator.plus(SymbolicTrafficFraction.fromGuard(selection(other, rib, dstIp)));
    }
    return numerator.div(denominator);
  }
}
