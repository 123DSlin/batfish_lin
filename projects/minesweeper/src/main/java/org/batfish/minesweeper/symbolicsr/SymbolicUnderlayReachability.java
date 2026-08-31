package org.batfish.minesweeper.symbolicsr;

import com.google.common.collect.ImmutableList;
import java.util.Optional;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Protocol-independent guarded reachability required by symbolic SR resolution. */
public interface SymbolicUnderlayReachability {
  /** Returns the guard for an exact underlay prefix advertisement, or empty if unreachable. */
  Optional<RouteGuard> prefixReachability(String node, String vrf, SrPrefix prefix, int algorithm);

  /** Exact selected forwarding next-hop branches for one underlay prefix. */
  default ImmutableList<SymbolicNextHopBranch> prefixNextHops(
      String node, String vrf, SrPrefix prefix, int algorithm) {
    return ImmutableList.of();
  }

  /** Returns a canonical adjacency/link guard; unsupported providers fail closed. */
  default Optional<SymbolicAdjacencyAvailability> adjacencyAvailability(
      String node, String vrf, String interfaceName) {
    return Optional.empty();
  }
}
