package org.batfish.minesweeper.symbolictraffic.parse;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.empty;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import java.nio.file.Paths;
import java.util.Collections;
import org.batfish.datamodel.Prefix;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of {@link TrafficGraph} parsing-layer structure. */
@RunWith(JUnit4.class)
public class TrafficGraphTest {

  @Test
  public void testInMemoryGraphIndexesEdges() {
    TrafficGraphEdge edge =
        new TrafficGraphEdge(
            "a_d", "a", "d", "GigabitEthernet0/1", "GigabitEthernet0/1", 95.0, false);
    TrafficFlow flow =
        new TrafficFlow(
            "x-ip-to-d",
            "x",
            Prefix.parse("5.5.5.5/32"),
            20.0,
            TrafficFlow.ForwardingType.IP,
            null,
            null);
    TrafficGraph graph =
        new TrafficGraph(
            Collections.singleton("a"),
            Collections.singleton(edge),
            Collections.singleton(flow));

    assertThat(graph.getOutgoingEdges("a"), contains(edge));
    assertThat(graph.getIncomingEdges("d"), contains(edge));
    assertThat(graph.getOutgoingEdges("d"), empty());
    assertThat(graph.getRouters().contains("x"), equalTo(true));
    assertThat(graph.getFlows(), contains(flow));
  }

  @Test
  public void testPseudoIncomingEdgeIsIncomingToReceiver() {
    TrafficGraphEdge ingress = new TrafficGraphEdge("l_R", "x", null, null, null, 0.0, true);
    TrafficGraph graph =
        new TrafficGraph(
            Collections.singleton("x"), Collections.singleton(ingress), Collections.emptyList());

    assertThat(graph.getIncomingEdges("x"), contains(ingress));
    assertThat(ingress.isPseudoIncoming(), equalTo(true));
  }

  @Test(expected = UnsupportedOperationException.class)
  public void testTrafficJsonParsingNotImplemented() {
    TrafficGraph.fromTrafficJson(Paths.get("traffic.json"));
  }
}
