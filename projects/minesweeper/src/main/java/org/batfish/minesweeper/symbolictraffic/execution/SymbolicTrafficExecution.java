package org.batfish.minesweeper.symbolictraffic.execution;

import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;

/**
 * YU Algorithm 1 {@code simulate(f)}: hop-iterated symbolic traffic execution.
 *
 * <p>Analogous to {@link org.batfish.minesweeper.smt.Encoder}: consumes an already-parsed {@link
 * TrafficGraph} and never opens configs or {@code traffic.json}. Per-router forwarding belongs in
 * {@link SymbolicTrafficForwarding}.
 */
public class SymbolicTrafficExecution {

  private final TrafficGraph _graph;

  private final SymbolicTrafficForwarding _forwarding;

  public SymbolicTrafficExecution(TrafficGraph graph) {
    _graph = graph;
    _forwarding = new SymbolicTrafficForwarding(graph);
  }

  public TrafficGraph getGraph() {
    return _graph;
  }

  SymbolicTrafficForwarding getForwarding() {
    return _forwarding;
  }

  /**
   * Run Algorithm 1 on one incoming flow.
   *
   * @throws UnsupportedOperationException until Algorithm 1 is implemented
   */
  public SymbolicTrafficMatrix simulate(TrafficFlow flow) {
    throw new UnsupportedOperationException(
        "YU Algorithm 1 simulate(f) is not implemented yet: " + flow);
  }

  /**
   * Aggregate {@code τ_l} over every flow in the parsed graph.
   *
   * @throws UnsupportedOperationException until Algorithm 1 is implemented
   */
  public SymbolicTrafficLoad trafficLoads() {
    throw new UnsupportedOperationException(
        "symbolic traffic load aggregation is not implemented yet");
  }
}
