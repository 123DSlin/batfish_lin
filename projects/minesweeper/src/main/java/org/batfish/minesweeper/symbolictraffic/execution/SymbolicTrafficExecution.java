package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
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
 * #simulate(TrafficFlow)} sums hop matrices {@code M_1 + … + M_{I'}} on real links; {@code τ_l}
 * must use that accumulated matrix, not {@code M_I}.
 *
 * <p>When the parsed graph has a finite {@code failureModel.maxFailures} {@code k}, each hop
 * matrix is replaced by its {@code k}-failure equivalent polynomial (YU §5.2 KREDUCE). That is
 * what makes Algorithm 1's output look like Figure 5 ({@code 1*x1 + 0.5*¬x1¬x2¬x3}) instead of a
 * full {@code 2^n} hop-accumulation DAG. In-flight mass that exists only under more than {@code k}
 * failures becomes 0 and ends the accumulated loop.
 *
 * <p>This class models <em>link traversal</em> only. Local delivery, RIB miss, unreachable
 * next-hop, and unreachable SR segment all produce an empty {@code forward} matrix: that mass is
 * not placed on a real link and does not reappear on a later hop. There is no separate
 * terminal-state matrix for delivered or dropped demand. After {@code I} hops any remaining
 * in-flight mass is discarded (TTL expiry) and is not propagated further.
 *
 * <p>A zero in-flight matrix ends the accumulated loop. Equality {@code M_i = M_{i-1}} is not a
 * stop condition, nor is “the accumulated matrix stopped changing”: on a DAG that equality is
 * usually the zero matrix after delivery, and on a forwarding loop a non-zero fixed point would
 * freeze circulating mass or under-count TTL traversals.
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

  public SymbolicTrafficExecution(TrafficGraph graph, SymbolicTrafficForwarding forwarding) {
    this(graph, DEFAULT_MAX_ITERATIONS, forwarding);
  }

  SymbolicTrafficExecution(
      TrafficGraph graph, int maxIterations, SymbolicTrafficForwarding forwarding) {
    if (graph == null) {
      throw new IllegalArgumentException("traffic graph cannot be null");
    }
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

  /**
   * Hops actually built by the last {@link #simulate} or {@link #simulateHopI} call.
   *
   * <p>{@link #simulateHopI} always reports {@code I}. {@link #simulate} reports {@code I'}: {@code
   * I} if in-flight traffic is still non-zero at TTL, otherwise the hop index of the first zero
   * in-flight matrix. Hop 1 is always executed, so a source that forwards nothing still reports
   * {@code 1} rather than {@code 0}. Before any call the value is {@code 0}.
   */
  int getLastCompletedHops() {
    return _lastCompletedHops;
  }

  SymbolicTrafficForwarding getForwarding() {
    return _forwarding;
  }

  /**
   * Accumulated STF of one flow on real links, {@code Σ_{i=1}^{I'} M_i}, excluding {@code l_R} and
   * {@code M_0}.
   *
   * <p>{@code I'} is {@code I} or the first hop whose in-flight matrix is zero. Each cell is a
   * hop-traversal fraction, not an occupancy in {@code [0, 1]}: the same real link is added once
   * per hop that carries the flow, so a forwarding loop can make a cell greater than 1. One call
   * injects one unit at the source; a later call does not reuse the previous matrices. This is
   * the matrix {@code trafficLoads} will scale by demand {@code V_f}.
   */
  public SymbolicTrafficMatrix simulate(TrafficFlow flow) {
    return run(flow, true);
  }

  /**
   * Paper listing: return {@code M_I} after exactly {@code I} hops. Does not stop early, does not
   * sum hops, and does not treat an intermediate zero matrix as a reason to return. A DAG shorter
   * than {@code I} hops therefore returns the zero matrix. Keep this for listing checks; do not
   * feed it to {@code τ_l} or {@link #trafficLoads()}.
   */
  public SymbolicTrafficMatrix simulateHopI(TrafficFlow flow) {
    return run(flow, false);
  }

  /**
   * Aggregate {@code τ_l = Σ_{f,S} V_f · M_f[l,S]} over every flow in the parsed graph.
   *
   * <p>{@code M_f} is {@link #simulate(TrafficFlow)}, the hop-accumulated real-link STF. Using
   * {@link #simulateHopI(TrafficFlow)} would make every traffic property a statement about hop
   * {@code I} only. TLP solving is not implemented here; it consumes {@link TrafficSimulation}.
   */
  public SymbolicTrafficLoad trafficLoads() {
    return simulateAll().getLoads();
  }

  /**
   * Run Algorithm 1 for every flow and keep both {@code M_f[l,S]} and {@code τ_l = Σ_{f,S} V_f ·
   * M_f[l,S]}.
   */
  public TrafficSimulation simulateAll() {
    Map<TrafficFlow, SymbolicTrafficMatrix> matrices = new LinkedHashMap<>();
    SymbolicTrafficLoad loads = new SymbolicTrafficLoad();
    for (TrafficFlow flow : _graph.getFlows()) {
      SymbolicTrafficMatrix matrix = simulate(flow);
      matrices.put(flow, matrix);
      double demand = flow.getDemandGbps();
      for (TrafficGraphEdge edge : matrix.edges()) {
        for (TrafficLabelStack stack : matrix.stacks(edge)) {
          loads.add(edge, matrix.get(edge, stack).times(demand));
        }
      }
    }
    return new TrafficSimulation(matrices, loads);
  }

  /** Per-flow accumulated matrices plus the aggregated symbolic loads. */
  public static final class TrafficSimulation {
    private final Map<TrafficFlow, SymbolicTrafficMatrix> _matrices;
    private final SymbolicTrafficLoad _loads;

    TrafficSimulation(
        Map<TrafficFlow, SymbolicTrafficMatrix> matrices, SymbolicTrafficLoad loads) {
      _matrices = new LinkedHashMap<>(matrices);
      _loads = loads;
    }

    public Map<TrafficFlow, SymbolicTrafficMatrix> getMatrices() {
      return Collections.unmodifiableMap(_matrices);
    }

    public SymbolicTrafficLoad getLoads() {
      return _loads;
    }
  }

  private SymbolicTrafficMatrix run(TrafficFlow flow, boolean accumulate) {
    if (flow == null) {
      throw new IllegalArgumentException("flow cannot be null");
    }
    if (!_graph.getRouters().contains(flow.getSource())) {
      throw new IllegalArgumentException(
          "flow source is not in the traffic graph: " + flow.getSource());
    }
    TrafficGraphEdge ingress =
        new TrafficGraphEdge(
            "l_" + flow.getSource(), flow.getSource(), null, null, null, 0.0, true);
    SymbolicTrafficMatrix previous = new SymbolicTrafficMatrix();
    previous.put(ingress, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());

    SymbolicTrafficMatrix accumulated = new SymbolicTrafficMatrix();
    SymbolicTrafficMatrix current = previous;
    List<String> routers = new ArrayList<>(_graph.getRouters());
    List<String> failureVars = _graph.getFailureVariables();
    int k = _graph.getMaxFailures();
    boolean reduce = k < Integer.MAX_VALUE && !failureVars.isEmpty();
    int completed = 0;
    for (int hop = 1; hop <= _maxIterations; hop++) {
      current = new SymbolicTrafficMatrix();
      for (String router : routers) {
        for (TrafficLabelStack stack : previous.stacks()) {
          SymbolicTrafficFraction omega =
              incomingOmega(router, stack, previous, flow, ingress, hop);
          if (omega.isZero()) {
            continue;
          }
          current.add(_forwarding.forward(router, flow, stack, omega));
        }
      }
      if (reduce) {
        current = current.kReduce(k, failureVars);
      }
      completed = hop;
      if (accumulate) {
        accumulated.addRealLinks(current);
        if (reduce) {
          accumulated = accumulated.kReduce(k, failureVars);
        }
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
