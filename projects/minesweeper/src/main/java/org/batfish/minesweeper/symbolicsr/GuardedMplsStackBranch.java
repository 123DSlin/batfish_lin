package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.List;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One concrete top-first MPLS label stack selected under a symbolic next-hop guard. */
public final class GuardedMplsStackBranch {
  private final ImmutableList<SrSidValue> _topFirstLabels;
  private final ImmutableList<SymbolicNextHopBranch> _nextHopDecisions;
  private final RouteGuard _guard;
  private final String _terminalNode;
  private final String _terminalVrf;

  GuardedMplsStackBranch(
      List<SrSidValue> topFirstLabels,
      List<SymbolicNextHopBranch> nextHopDecisions,
      RouteGuard guard,
      String terminalNode,
      String terminalVrf) {
    _topFirstLabels = ImmutableList.copyOf(requireNonNull(topFirstLabels));
    _nextHopDecisions = ImmutableList.copyOf(requireNonNull(nextHopDecisions));
    _guard = requireNonNull(guard);
    _terminalNode = requireNonNull(terminalNode);
    _terminalVrf = requireNonNull(terminalVrf);
  }

  public ImmutableList<SrSidValue> getTopFirstLabels() {
    return _topFirstLabels;
  }

  public ImmutableList<SymbolicNextHopBranch> getNextHopDecisions() {
    return _nextHopDecisions;
  }

  public RouteGuard getGuard() {
    return _guard;
  }

  public String getTerminalNode() {
    return _terminalNode;
  }

  public String getTerminalVrf() {
    return _terminalVrf;
  }
}
