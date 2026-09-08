package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.List;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * YU Algorithm 1 {@code simulate(f)}: hop-iterated symbolic traffic execution.
 *
 * <p>Analogous to {@link org.batfish.minesweeper.smt.Encoder}: consumes an already-parsed {@link
 * TrafficGraph} and never opens configs or {@code traffic.json}. Per-router forwarding is {@link
 * SymbolicTrafficForwarding} (YU Algorithm 2).
 *
 * <p>This method follows the paper listing: initialize {@code M0[l_R, ∅] = 1}, then for {@code i =
 * 1..I} build a fresh {@code M_i} by summing incoming STF into {@code ω} and adding {@code
 * forward(R, f, S, ω)}. It returns {@code M_I} (exactly-{@code I}-hop STF), not the sum over hops.
 */
public class SymbolicTrafficExecution {

  /** IPv4 TTL; the paper takes the maximum iteration number from TTL. */
  public static final int DEFAULT_MAX_ITERATIONS = 255;

  private final TrafficGraph _graph;

  private final int _maxIterations;

  private final SymbolicTrafficForwarding _forwarding;

  public SymbolicTrafficExecution(TrafficGraph graph) {
    this(graph, DEFAULT_MAX_ITERATIONS, new SymbolicTrafficForwarding(graph));
  }

  public SymbolicTrafficExecution(TrafficGraph graph, int maxIterations) {
    this(graph, maxIterations, new SymbolicTrafficForwarding(graph));
  }

  SymbolicTrafficExecution(
      TrafficGraph graph, int maxIterations, SymbolicTrafficForwarding forwarding) {
    if (maxIterations < 1) {
      throw new IllegalArgumentException("maximum iteration number must be positive");
    }
    _graph = graph;
    _maxIterations = maxIterations;
    _forwarding = forwarding;
  }

  public TrafficGraph getGraph() {
    return _graph;
  }

  public int getMaxIterations() {
    return _maxIterations;
  }

  SymbolicTrafficForwarding getForwarding() {
    return _forwarding;
  }

  /**
   * Run Algorithm 1 on one incoming flow.
   *
   * <p>Constructs the pseudo ingress {@code l_R} locally and does not mutate {@link TrafficGraph}.
   */
  public SymbolicTrafficMatrix simulate(TrafficFlow flow) {
    TrafficGraphEdge ingress =
        new TrafficGraphEdge(
            "l_" + flow.getSource(), flow.getSource(), null, null, null, 0.0, true);
    SymbolicTrafficMatrix previous = new SymbolicTrafficMatrix();
    previous.put(ingress, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());

    SymbolicTrafficMatrix current = previous;
    for (int hop = 1; hop <= _maxIterations; hop++) {
      current = new SymbolicTrafficMatrix();
      for (String router : _graph.getRouters()) {
        for (TrafficLabelStack stack : previous.stacks()) {
          SymbolicTrafficFraction omega = incomingOmega(router, stack, previous, flow, ingress);
          current.add(_forwarding.forward(router, flow, stack, omega));
        }
      }
      previous = current;
    }
    return current;
  }

  /**
   * Aggregate {@code τ_l} over every flow in the parsed graph.
   *
   * @throws UnsupportedOperationException until STL aggregation is implemented
   */
  public SymbolicTrafficLoad trafficLoads() {
    throw new UnsupportedOperationException(
        "symbolic traffic load aggregation is not implemented yet");
  }

  /**
   * Line 8: {@code ω} is the sum of {@code M_{i-1}[l, S]} over incoming links of {@code R},
   * including {@code l_R} when {@code R} is the flow's receiving router.
   */
  private SymbolicTrafficFraction incomingOmega(
      String router,
      TrafficLabelStack stack,
      SymbolicTrafficMatrix previous,
      TrafficFlow flow,
      TrafficGraphEdge ingress) {
    SymbolicTrafficFraction omega = SymbolicTrafficFraction.zero();
    List<TrafficGraphEdge> incoming = new ArrayList<>(_graph.getIncomingEdges(router));
    for (TrafficGraphEdge edge : incoming) {
      if (edge.isPseudoIncoming()) {
        continue;
      }
      omega = omega.plus(previous.get(edge, stack));
    }
    if (router.equals(flow.getSource())) {
      omega = omega.plus(previous.get(ingress, stack));
    }
    return omega;
  }
}
