package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.List;
import org.batfish.datamodel.Ip;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/**
 * YU encoding of route selection {@code s_r} and (weighted) ECMP {@code c_r}.
 *
 * <p>{@code s^{dstip}_r = 0} if {@code dstip} does not match {@code r}; otherwise {@code g_r ∧ ∧_{r'
 * ≺ r} ¬g_{r'}}. {@code c^{dstip}_r = s_r / Σ_{r'} s_{r'}}.
 */
public final class RouteSelectionEncoding {

  private RouteSelectionEncoding() {}

  /** {@code r1 ≺ r2}: {@code r1} is strictly more preferred than {@code r2}. */
  public static boolean strictlyPreferred(ForwardingRule better, ForwardingRule worse) {
    int lengthDelta = better.getPrefix().getPrefixLength() - worse.getPrefix().getPrefixLength();
    if (lengthDelta != 0) {
      return lengthDelta > 0;
    }
    return better.getPreference() < worse.getPreference();
  }

  public static RouteGuard selection(ForwardingRule rule, List<ForwardingRule> rib, Ip dstIp) {
    if (!rule.matches(dstIp)) {
      return rule.getAvailability().and(rule.getAvailability().not());
    }
    RouteGuard selected = rule.getAvailability();
    for (ForwardingRule other : rib) {
      if (other != rule && other.matches(dstIp) && strictlyPreferred(other, rule)) {
        selected = selected.and(other.getAvailability().not());
      }
    }
    return selected;
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
