package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import java.util.Collections;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/**
 * Tests of the Algorithm 1/2 execution package. Parsing is not used here: tests build a {@link
 * TrafficGraph} in memory.
 */
@RunWith(JUnit4.class)
public class SymbolicTrafficExecutionTest {

  private static TrafficGraph graph() {
    TrafficFlow flow =
        new TrafficFlow(
            "x-ip-to-d",
            "x",
            Prefix.parse("5.5.5.5/32"),
            20.0,
            TrafficFlow.ForwardingType.IP,
            null,
            null);
    return new TrafficGraph(
        Collections.singleton("x"), Collections.emptyList(), Collections.singleton(flow));
  }

  @Test
  public void testEmptyLabelStackIsYuEmptyStack() {
    assertThat(TrafficLabelStack.empty().isEmpty(), equalTo(true));
    assertThat(TrafficLabelStack.empty(), equalTo(new TrafficLabelStack(Collections.emptyList())));
  }

  @Test(expected = UnsupportedOperationException.class)
  public void testSimulateNotImplemented() {
    TrafficGraph g = graph();
    new SymbolicTrafficExecution(g).simulate(g.getFlows().get(0));
  }

  @Test(expected = UnsupportedOperationException.class)
  public void testForwardNotImplemented() {
    TrafficGraph g = graph();
    new SymbolicTrafficExecution(g)
        .getForwarding()
        .forward("x", g.getFlows().get(0), TrafficLabelStack.empty(), 1);
  }
}
