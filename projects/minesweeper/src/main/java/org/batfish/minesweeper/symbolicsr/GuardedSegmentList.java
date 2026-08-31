package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.List;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One ordered SID sequence and its exact symbolic execution guard. */
public final class GuardedSegmentList {
  private final ImmutableList<GuardedSidEntry> _segments;
  private final RouteGuard _availabilityGuard;
  private final String _terminalNode;
  private final String _terminalVrf;

  GuardedSegmentList(
      List<GuardedSidEntry> segments,
      RouteGuard availabilityGuard,
      String terminalNode,
      String terminalVrf) {
    _segments = ImmutableList.copyOf(requireNonNull(segments));
    _availabilityGuard = requireNonNull(availabilityGuard);
    _terminalNode = requireNonNull(terminalNode);
    _terminalVrf = requireNonNull(terminalVrf);
  }

  public ImmutableList<GuardedSidEntry> getSegments() {
    return _segments;
  }

  public RouteGuard getAvailabilityGuard() {
    return _availabilityGuard;
  }

  public String getTerminalNode() {
    return _terminalNode;
  }

  public String getTerminalVrf() {
    return _terminalVrf;
  }
}
