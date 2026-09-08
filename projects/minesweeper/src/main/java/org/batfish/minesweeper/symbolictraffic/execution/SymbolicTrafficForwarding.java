package org.batfish.minesweeper.symbolictraffic.execution;

import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;

/**
 * YU Algorithm 2 {@code forward(R, f, S, ω)}: symbolic forwarding at one router.
 *
 * <p>Analogous to {@link org.batfish.minesweeper.smt.EncoderSlice}. Algorithm 1 calls this each
 * iteration; the body is not implemented yet.
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
      String router,
      TrafficFlow flow,
      TrafficLabelStack stack,
      SymbolicTrafficFraction incomingFraction) {
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
