package org.batfish.minesweeper.symbolicsr;

import static com.google.common.base.Preconditions.checkArgument;
import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.List;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Top-first MPLS segment stack plan with deferred next-hop-dependent labels retained. */
public final class MplsLabelPlan {
  private final ImmutableList<MplsLabelInstruction> _topFirstInstructions;
  private final RouteGuard _availabilityGuard;
  private final String _terminalNode;
  private final String _terminalVrf;

  MplsLabelPlan(
      List<MplsLabelInstruction> topFirstInstructions,
      RouteGuard availabilityGuard,
      String terminalNode,
      String terminalVrf) {
    _topFirstInstructions = ImmutableList.copyOf(requireNonNull(topFirstInstructions));
    checkArgument(!_topFirstInstructions.isEmpty(), "MPLS label plan must not be empty");
    _availabilityGuard = requireNonNull(availabilityGuard);
    _terminalNode = requireNonNull(terminalNode);
    _terminalVrf = requireNonNull(terminalVrf);
  }

  /** Instructions are in execution order, which is also MPLS stack top-to-bottom order. */
  public ImmutableList<MplsLabelInstruction> getTopFirstInstructions() {
    return _topFirstInstructions;
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
