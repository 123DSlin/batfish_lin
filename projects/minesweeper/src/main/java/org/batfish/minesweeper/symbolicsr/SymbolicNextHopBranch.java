package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One parser-derived forwarding next hop selected under a symbolic guard. */
public final class SymbolicNextHopBranch {
  private final SymbolicAdjacencyEndpoint _nextHop;
  private final LinkFailureKey _linkFailureDependency;
  private final RouteGuard _guard;

  public SymbolicNextHopBranch(
      SymbolicAdjacencyEndpoint nextHop, LinkFailureKey linkFailureDependency, RouteGuard guard) {
    _nextHop = requireNonNull(nextHop, "next hop must be provided");
    _linkFailureDependency =
        requireNonNull(linkFailureDependency, "link failure dependency must be provided");
    _guard = requireNonNull(guard, "guard must be provided");
  }

  public SymbolicAdjacencyEndpoint getNextHop() {
    return _nextHop;
  }

  public LinkFailureKey getLinkFailureDependency() {
    return _linkFailureDependency;
  }

  public RouteGuard getGuard() {
    return _guard;
  }
}
