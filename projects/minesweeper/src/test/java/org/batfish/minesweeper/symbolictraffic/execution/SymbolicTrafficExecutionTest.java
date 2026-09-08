package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.empty;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/**
 * Checks YU Algorithm 1 {@code simulate(f)} against a stand-in {@code forward}. Algorithm 2 has
 * its own tests; the stand-in is only used to isolate the hop loop.
 */
@RunWith(JUnit4.class)
public class SymbolicTrafficExecutionTest {

  private static final Prefix DEST = Prefix.parse("5.5.5.5/32");

  private static TrafficFlow flow(String source) {
    return new TrafficFlow(
        source + "-to-d", source, DEST, 20.0, TrafficFlow.ForwardingType.IP, null, null);
  }

  private static TrafficGraphEdge edge(String id, String from, String to) {
    return new TrafficGraphEdge(id, from, to, "Ethernet0", "Ethernet0", 95.0, false);
  }

  private static TrafficGraph graph(TrafficFlow flow, TrafficGraphEdge... edges) {
    List<String> routers = new ArrayList<>();
    for (TrafficGraphEdge edge : edges) {
      routers.add(edge.getRouter());
      if (edge.getPeer() != null) {
        routers.add(edge.getPeer());
      }
    }
    routers.add(flow.getSource());
    return new TrafficGraph(routers, Arrays.asList(edges), Collections.singleton(flow));
  }

  @Test
  public void testEmptyLabelStackIsYuEmptyStack() {
    assertThat(TrafficLabelStack.empty().isEmpty(), equalTo(true));
    assertThat(TrafficLabelStack.empty(), equalTo(new TrafficLabelStack(Collections.emptyList())));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testMaxIterationsMustBePositive() {
    new SymbolicTrafficExecution(graph(flow("a")), 0);
  }

  @Test
  public void testDefaultMaxIterationsIsTtl() {
    assertThat(
        new SymbolicTrafficExecution(graph(flow("a"))).getMaxIterations(),
        equalTo(SymbolicTrafficExecution.DEFAULT_MAX_ITERATIONS));
  }

  @Test
  public void testEmptyRibForwardsNothing() {
    TrafficFlow f = flow("x");
    TrafficGraph g = graph(f);
    SymbolicTrafficMatrix matrix =
        new SymbolicTrafficExecution(g)
            .getForwarding()
            .forward("x", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(matrix.isZero(), equalTo(true));
  }

  @Test
  public void testFirstHopPlacesM0IngressOntoOutgoingLinks() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    CopyOmegaForward forward = new CopyOmegaForward(g);
    SymbolicTrafficMatrix result =
        new SymbolicTrafficExecution(g, 1, forward).simulateHopI(f);

    assertThat(result.get(ab, TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
    assertThat(result.edges(), containsInAnyOrder(ab));
    assertThat(
        forward.omegas("a", TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
    assertThat(
        forward.omegas("b", TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.zero()));
  }

  @Test
  public void testReturnedMatrixIsExactlyHopI() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge bc = edge("b_c", "b", "c");
    TrafficGraph g = graph(f, ab, bc);
    CopyOmegaForward forward = new CopyOmegaForward(g);

    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forward).simulateHopI(f);
    assertThat(hop1.get(ab, TrafficLabelStack.empty()).isOne(), equalTo(true));
    assertThat(hop1.get(bc, TrafficLabelStack.empty()).isZero(), equalTo(true));

    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(g, 2, new CopyOmegaForward(g)).simulateHopI(f);
    assertThat(hop2.get(ab, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(hop2.get(bc, TrafficLabelStack.empty()).isOne(), equalTo(true));
  }

  @Test
  public void testIncomingOmegaSumsAllIncomingLinks() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraphEdge bd = edge("b_d", "b", "d");
    TrafficGraphEdge cd = edge("c_d", "c", "d");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, ab, ac, bd, cd, de);
    CopyOmegaForward forward = new CopyOmegaForward(g);

    SymbolicTrafficMatrix hop3 = new SymbolicTrafficExecution(g, 3, forward).simulateHopI(f);

    assertThat(hop3.get(de, TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
    assertThat(
        forward.omegas("d", TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
  }

  @Test
  public void testGraphPseudoIncomingDoesNotInflateOmega() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge leftover =
        new TrafficGraphEdge("l_stale", "b", null, null, null, 0.0, true);
    TrafficGraph g = graph(f, ab, leftover);
    CopyOmegaForward forward = new CopyOmegaForward(g);
    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forward).simulateHopI(f);
    assertThat(hop1.get(ab, TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
    assertThat(
        forward.omegas("a", TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.one()));
    assertThat(
        forward.omegas("b", TrafficLabelStack.empty()), equalTo(SymbolicTrafficFraction.zero()));
  }

  @Test
  public void testLabelStackIsPropagatedAsAMatrixColumn() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge bc = edge("b_c", "b", "c");
    TrafficGraph g = graph(f, ab, bc);
    TrafficLabelStack pushed = new TrafficLabelStack(Collections.singletonList("E"));
    PushThenCopyForward forward = new PushThenCopyForward(g, "a", pushed);

    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forward).simulateHopI(f);
    assertThat(hop1.get(ab, pushed), equalTo(SymbolicTrafficFraction.one()));
    assertThat(hop1.get(ab, TrafficLabelStack.empty()).isZero(), equalTo(true));

    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(g, 2, new PushThenCopyForward(g, "a", pushed)).simulateHopI(f);
    assertThat(hop2.get(bc, pushed), equalTo(SymbolicTrafficFraction.one()));
    assertThat(hop2.get(bc, TrafficLabelStack.empty()).isZero(), equalTo(true));
  }

  @Test
  public void testHopTwoCallsJoinRouterWithPushedStack() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    TrafficLabelStack pushed = new TrafficLabelStack(Collections.singletonList("E"));
    PushThenCopyForward forward = new PushThenCopyForward(g, "a", pushed);
    new SymbolicTrafficExecution(g, 2, forward).simulateHopI(f);

    assertThat(forward.omegas("b", pushed), equalTo(SymbolicTrafficFraction.one()));
    assertThat(forward.calledStacks("b"), containsInAnyOrder(pushed));
  }

  @Test
  public void testSinkRouterContributesEmptyForward() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(g, 2, new CopyOmegaForward(g)).simulateHopI(f);
    assertThat(hop2.isZero(), equalTo(true));
    assertThat(hop2.edges(), empty());
  }

  @Test(expected = UnsupportedOperationException.class)
  public void testTrafficLoadsNotImplemented() {
    new SymbolicTrafficExecution(graph(flow("a"))).trafficLoads();
  }

  @Test
  public void testSimulateAccumulatesEveryHopOnRealLinks() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge bc = edge("b_c", "b", "c");
    TrafficGraph g = graph(f, ab, bc);
    SymbolicTrafficExecution execution =
        new SymbolicTrafficExecution(g, 10, new CopyOmegaForward(g));
    SymbolicTrafficMatrix accumulated = execution.simulate(f);

    assertThat(accumulated.get(ab, TrafficLabelStack.empty()).isOne(), equalTo(true));
    assertThat(accumulated.get(bc, TrafficLabelStack.empty()).isOne(), equalTo(true));
    assertThat(execution.getLastCompletedHops() < 10, equalTo(true));
  }

  @Test
  public void testSimulateHopIDoesNotStopEarly() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    SymbolicTrafficExecution execution =
        new SymbolicTrafficExecution(g, 4, new CopyOmegaForward(g));
    SymbolicTrafficMatrix hopI = execution.simulateHopI(f);
    assertThat(hopI.isZero(), equalTo(true));
    assertThat(execution.getLastCompletedHops(), equalTo(4));
  }

  @Test
  public void testPseudoIngressIsNotReinjectedAfterHopOne() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    CopyOmegaForward forward = new CopyOmegaForward(g);
    new SymbolicTrafficExecution(g, 3, forward).simulateHopI(f);

    int nonZeroSourceCalls = forward.nonZeroOmegaCalls("a");
    assertThat(nonZeroSourceCalls, equalTo(1));
  }

  /**
   * Stand-in for Algorithm 2: copy {@code ω} equally onto every outgoing edge, keeping the same
   * stack. Zero {@code ω} yields an empty matrix.
   */
  private static class CopyOmegaForward extends SymbolicTrafficForwarding {

    private final List<ForwardCall> _calls;

    CopyOmegaForward(TrafficGraph graph) {
      super(graph);
      _calls = new ArrayList<>();
    }

    @Override
    SymbolicTrafficMatrix forward(
        String router,
        TrafficFlow flow,
        TrafficLabelStack stack,
        SymbolicTrafficFraction incomingFraction) {
      _calls.add(new ForwardCall(router, stack, incomingFraction));
      SymbolicTrafficMatrix matrix = new SymbolicTrafficMatrix();
      List<TrafficGraphEdge> outgoing = getGraph().getOutgoingEdges(router);
      if (incomingFraction.isZero() || outgoing.isEmpty()) {
        return matrix;
      }
      SymbolicTrafficFraction share =
          new SymbolicTrafficFraction(incomingFraction.getValue() / outgoing.size());
      for (TrafficGraphEdge edge : outgoing) {
        matrix.put(edge, stack, share);
      }
      return matrix;
    }

    SymbolicTrafficFraction omegas(String router, TrafficLabelStack stack) {
      SymbolicTrafficFraction sum = SymbolicTrafficFraction.zero();
      for (ForwardCall call : _calls) {
        if (call._router.equals(router) && call._stack.equals(stack)) {
          sum = sum.plus(call._omega);
        }
      }
      return sum;
    }

    List<TrafficLabelStack> calledStacks(String router) {
      List<TrafficLabelStack> stacks = new ArrayList<>();
      for (ForwardCall call : _calls) {
        if (call._router.equals(router) && !call._omega.isZero()) {
          stacks.add(call._stack);
        }
      }
      return stacks;
    }

    int nonZeroOmegaCalls(String router) {
      int count = 0;
      for (ForwardCall call : _calls) {
        if (call._router.equals(router) && !call._omega.isZero()) {
          count++;
        }
      }
      return count;
    }
  }

  /**
   * Like {@link CopyOmegaForward}, but {@code pushRouter} emits {@code pushed} instead of {@code S}.
   */
  private static final class PushThenCopyForward extends CopyOmegaForward {

    private final String _pushRouter;

    private final TrafficLabelStack _pushed;

    PushThenCopyForward(TrafficGraph graph, String pushRouter, TrafficLabelStack pushed) {
      super(graph);
      _pushRouter = pushRouter;
      _pushed = pushed;
    }

    @Override
    SymbolicTrafficMatrix forward(
        String router,
        TrafficFlow flow,
        TrafficLabelStack stack,
        SymbolicTrafficFraction incomingFraction) {
      TrafficLabelStack outStack = router.equals(_pushRouter) ? _pushed : stack;
      SymbolicTrafficMatrix recorded = super.forward(router, flow, stack, incomingFraction);
      if (outStack.equals(stack)) {
        return recorded;
      }
      SymbolicTrafficMatrix rewritten = new SymbolicTrafficMatrix();
      for (TrafficGraphEdge edge : recorded.edges()) {
        rewritten.put(edge, outStack, recorded.get(edge, stack));
      }
      return rewritten;
    }
  }

  private static final class ForwardCall {
    private final String _router;
    private final TrafficLabelStack _stack;
    private final SymbolicTrafficFraction _omega;

    private ForwardCall(String router, TrafficLabelStack stack, SymbolicTrafficFraction omega) {
      _router = router;
      _stack = stack;
      _omega = omega;
    }

    @Override
    public boolean equals(Object o) {
      if (!(o instanceof ForwardCall)) {
        return false;
      }
      ForwardCall other = (ForwardCall) o;
      return Objects.equals(_router, other._router)
          && Objects.equals(_stack, other._stack)
          && Objects.equals(_omega, other._omega);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_router, _stack, _omega);
    }
  }
}
