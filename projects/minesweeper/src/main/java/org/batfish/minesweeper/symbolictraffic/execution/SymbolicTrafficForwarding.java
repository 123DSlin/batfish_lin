package org.batfish.minesweeper.symbolictraffic.execution;

import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;

/**
 * YU Algorithm 2 {@code forward(R, f, S, ω)}: symbolic forwarding at one router.
 *
 * <p>Analogous to {@link org.batfish.minesweeper.smt.EncoderSlice} in role (per-unit encoding) and
 * kept package-private so Algorithm 1 is the only public driver. Not implemented; Algorithm 1 will
 * call this after it is specified.
 */
class SymbolicTrafficForwarding {

  private final TrafficGraph _graph;

  SymbolicTrafficForwarding(TrafficGraph graph) {
    _graph = graph;
  }

  TrafficGraph getGraph() {
    return _graph;
  }

  SymbolicTrafficMatrix forward(
      String router, TrafficFlow flow, TrafficLabelStack stack, Object incomingFraction) {
    throw new UnsupportedOperationException(
        "YU Algorithm 2 forward is not implemented yet: "
            + router
            + " "
            + flow
            + " "
            + stack
            + " "
            + incomingFraction);
  }
}
