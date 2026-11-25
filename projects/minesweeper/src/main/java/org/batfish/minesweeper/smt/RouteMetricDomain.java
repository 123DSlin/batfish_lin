package org.batfish.minesweeper.smt;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import java.util.Collection;
import javax.annotation.Nullable;
import org.batfish.minesweeper.Protocol;

/** Domains of the arithmetic metric stored in symbolic route records. */
final class RouteMetricDomain {

  static final long ENVIRONMENT_EXCLUSIVE_UPPER_BOUND = 1L << 8;
  static final long LEGACY_EXCLUSIVE_UPPER_BOUND = 1L << 16;
  static final String BGP_DOMAIN = "nonnegative-integer";

  private RouteMetricDomain() {}

  /**
   * BGP metric represents AS-path length, not a 16-bit field. Prepend and later session hops must
   * remain representable. An overall BEST record in a BGP-only router uses that same arithmetic
   * domain (connected and static alternatives contribute zero). Mixed IGP/BGP BEST records retain
   * the existing bound until they receive a protocol-conditional domain.
   *
   * <p>The external-environment bound remains an explicit assumption. This policy does not change
   * the separate, optional protocol overflow semantics in {@link TransferSSA}.
   */
  static @Nullable Long exclusiveUpperBound(
      Protocol protocol, Collection<Protocol> routerProtocols, boolean environment) {
    if (environment) {
      return ENVIRONMENT_EXCLUSIVE_UPPER_BOUND;
    }
    boolean bgpOnlyBest =
        protocol.isBest()
            && routerProtocols.contains(Protocol.BGP)
            && routerProtocols.stream().noneMatch(p -> p.isOspf() || p.isIsis());
    if (protocol.isBgp() || bgpOnlyBest) {
      return null;
    }
    return LEGACY_EXCLUSIVE_UPPER_BOUND;
  }

  static BoolExpr constraints(Context context, ArithExpr metric, @Nullable Long upperBound) {
    BoolExpr nonnegative = context.mkGe(metric, context.mkInt(0));
    return upperBound == null
        ? nonnegative
        : context.mkAnd(nonnegative, context.mkLt(metric, context.mkInt(upperBound)));
  }
}
