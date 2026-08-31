package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.Optional;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.minesweeper.symbolicroute.GuardedRib;
import org.batfish.minesweeper.symbolicroute.GuardedRibEntry;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteNetwork;

/** IS-IS L1/L2 implementation of exact guarded prefix reachability. */
public final class IsisUnderlayReachability implements SymbolicUnderlayReachability {
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l1;
  private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _l2;

  public IsisUnderlayReachability(
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l1,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l2) {
    _l1 = requireNonNull(l1, "L1 network must be provided");
    _l2 = requireNonNull(l2, "L2 network must be provided");
  }

  @Override
  public Optional<RouteGuard> prefixReachability(
      String node, String vrf, SrPrefix prefix, int algorithm) {
    requireNonNull(node, "node must be provided");
    requireNonNull(vrf, "VRF must be provided");
    requireNonNull(prefix, "prefix must be provided");
    if (prefix.getFamily() != SrPrefix.Family.IPV4 || algorithm != 0) {
      return Optional.empty();
    }
    RouteGuard combined = null;
    combined = combine(combined, _l1.getRib(node), vrf, prefix);
    combined = combine(combined, _l2.getRib(node), vrf, prefix);
    return Optional.ofNullable(combined == null ? null : combined.simplify());
  }

  private static RouteGuard combine(
      RouteGuard accumulated,
      GuardedRib<AnnotatedRoute<IsisRoute>> rib,
      String vrf,
      SrPrefix prefix) {
    RouteGuard result = accumulated;
    for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry : rib.getEntries()) {
      if (!entry.getSymbolicRoute().getKey().getVrf().equals(vrf)
          || !entry.getSymbolicRoute().getKey().getNetwork().equals(prefix.getIpv4())
          || !entry.getSelectionGuard().isSatisfiable()) {
        continue;
      }
      result =
          result == null
              ? entry.getSelectionGuard()
              : result.or(entry.getSelectionGuard()).simplify();
    }
    return result;
  }
}
