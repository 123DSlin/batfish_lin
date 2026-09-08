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
 * <p>{@link #simulateHopI(TrafficFlow)} is the paper listing: it returns {@code M_I}, the
 * exactly-{@code I}-hop matrix. That is not a flow's STF on every link. {@link
 * #simulate(TrafficFlow)} sums hop matrices {@code M_1 + … + M_I} on real links; {@code τ_l} must
 * use that accumulated matrix, not {@code M_I}.
 *
 * <p>A zero in-flight matrix ends the accumulated loop. Equality {@code M_i = M_{i-1}} is not a
 * stop condition: on a DAG that equality is usually the zero matrix after delivery, and on a
 * forwarding loop a non-zero fixed point would either freeze circulating mass or under-count TTL
 * traversals.
 */
public class SymbolicTrafficExecution {

  /** IPv4 TTL; the paper takes the maximum iteration number from TTL. */
  public static final int DEFAULT_MAX_ITERATIONS = 255;

  private final TrafficGraph _graph;

  private final int _maxIterations;

  private final SymbolicTrafficForwarding _forwarding;

  private int _lastCompletedHops;

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
    _lastCompletedHops = 0;
  }

  public TrafficGraph getGraph() {
    return _graph;
  }

  public int getMaxIterations() {
    return _maxIterations;
  }

  /** Hops actually built by the last {@link #simulate} or {@link #simulateHopI} call. */
  int getLastCompletedHops() {
    return _lastCompletedHops;
  }

  SymbolicTrafficForwarding getForwarding() {
    return _forwarding;
  }

  /**
   * Accumulated STF of one flow on real links, {@code Σ_{i=1}^{I'} M_i}, excluding {@code l_R}.
   *
   * <p>{@code I'} is {@code I} or the first hop whose in-flight matrix is zero. This is the matrix
   * {@code trafficLoads} will scale by demand {@code V_f}.
   */
  public SymbolicTrafficMatrix simulate(TrafficFlow flow) {
    return run(flow, true);
  }

  /**
   * Paper listing: return {@code M_I} after exactly {@code I} hops. Does not stop early and does
   * not sum hops. Keep this for listing checks; do not feed it to {@code τ_l}.
   */
  public SymbolicTrafficMatrix simulateHopI(TrafficFlow flow) {
    return run(flow, false);
  }

  /**
   * Aggregate {@code τ_l = Σ_{f,S} V_f · M_f[l,S]}.
   *
   * <p>{@code M_f} must be {@link #simulate(TrafficFlow)}, the hop-accumulated real-link STF. Using
   * {@link #simulateHopI(TrafficFlow)} would make every traffic property a statement about hop
   * {@code I} only. Demand scaling, destination delivery, and TLP are not implemented here yet.
   *
   * @throws UnsupportedOperationException until STL aggregation is implemented
   */
  public SymbolicTrafficLoad trafficLoads() {
    throw new UnsupportedOperationException(
        "symbolic traffic load aggregation is not implemented yet");
  }

  private SymbolicTrafficMatrix run(TrafficFlow flow, boolean accumulate) {
    TrafficGraphEdge ingress =
        new TrafficGraphEdge(
            "l_" + flow.getSource(), flow.getSource(), null, null, null, 0.0, true);
    SymbolicTrafficMatrix previous = new SymbolicTrafficMatrix();
    previous.put(ingress, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());

    SymbolicTrafficMatrix accumulated = new SymbolicTrafficMatrix();
    SymbolicTrafficMatrix current = previous;
    int completed = 0;
    for (int hop = 1; hop <= _maxIterations; hop++) {
      current = new SymbolicTrafficMatrix();
      for (String router : _graph.getRouters()) {
        for (TrafficLabelStack stack : previous.stacks()) {
          SymbolicTrafficFraction omega =
              incomingOmega(router, stack, previous, flow, ingress, hop);
          current.add(_forwarding.forward(router, flow, stack, omega));
        }
      }
      completed = hop;
      if (accumulate) {
        accumulated.addRealLinks(current);
        if (current.isZero()) {
          break;
        }
      }
      previous = current;
    }
    _lastCompletedHops = completed;
    return accumulate ? accumulated : current;
  }

  /**
   * Line 8: {@code ω} is the sum of {@code M_{i-1}[l, S]} over real incoming links of {@code R}.
   * The constructed {@code l_R} is added only on hop 1 at the flow source, so a leftover graph
   * pseudo incoming cannot inject a second unit of mass.
   */
  private SymbolicTrafficFraction incomingOmega(
      String router,
      TrafficLabelStack stack,
      SymbolicTrafficMatrix previous,
      TrafficFlow flow,
      TrafficGraphEdge ingress,
      int hop) {
    SymbolicTrafficFraction omega = SymbolicTrafficFraction.zero();
    List<TrafficGraphEdge> incoming = new ArrayList<>(_graph.getIncomingEdges(router));
    for (TrafficGraphEdge edge : incoming) {
      if (edge.isPseudoIncoming()) {
        continue;
      }
      omega = omega.plus(previous.get(edge, stack));
    }
    if (hop == 1 && router.equals(flow.getSource())) {
      omega = omega.plus(previous.get(ingress, stack));
    }
    return omega;
  }
}
