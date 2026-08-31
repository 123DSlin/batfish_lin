package org.batfish.minesweeper.symbolicsr;

import java.util.Optional;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Protocol-independent guarded reachability required by symbolic SR resolution. */
public interface SymbolicUnderlayReachability {
  /** Returns the guard for an exact underlay prefix advertisement, or empty if unreachable. */
  Optional<RouteGuard> prefixReachability(String node, String vrf, SrPrefix prefix, int algorithm);

  /** Returns a canonical adjacency/link guard; unsupported providers fail closed. */
  default Optional<RouteGuard> adjacencyAvailability(
      String node, String vrf, String interfaceName) {
    return Optional.empty();
  }
}
