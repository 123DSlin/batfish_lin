package org.batfish.minesweeper.symbolictraffic.parse;

import static org.hamcrest.Matchers.contains;
import static org.hamcrest.Matchers.empty;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.Path;
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

  @Test(expected = UnsupportedOperationException.class)
  public void testRoutersViewIsUnmodifiable() {
    TrafficGraph graph =
        new TrafficGraph(
            Collections.singleton("a"), Collections.emptyList(), Collections.emptyList());
    graph.getRouters().add("b");
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

  @Test(expected = IllegalArgumentException.class)
  public void testTrafficJsonParsingRequiresTrafficJson() {
    TrafficGraph.fromTrafficJson(Paths.get("traffic.json"));
  }

  @Test
  public void testParseFromTrafficJson() throws Exception {
    String json =
        "{\n"
            + "  \"flows\": [\n"
            + "    {\"id\": \"f1\", \"source\": \"a\", \"destination\": \"5.5.5.5/32\",\n"
            + "     \"demandGbps\": 20.0, \"forwarding\": \"IP\"}\n"
            + "  ],\n"
            + "  \"links\": [\n"
            + "    {\"id\": \"a_d\",\n"
            + "     \"endpoint1\": {\"node\": \"a\", \"interface\": \"ge-0/0\"},\n"
            + "     \"endpoint2\": {\"node\": \"d\", \"interface\": \"ge-0/1\"},\n"
            + "     \"capacityGbps\": 100.0}\n"
            + "  ]\n"
            + "}";

    Path path = Files.createTempFile("traffic_graph_test", ".json");
    Files.writeString(path, json);

    TrafficGraph graph = TrafficGraph.fromTrafficJson(path);

    assertThat(graph.getFlows().size(), equalTo(1));
    assertThat(graph.getRouters().contains("a"), equalTo(true));
    assertThat(graph.getRouters().contains("d"), equalTo(true));
    assertThat(graph.getEdges().size(), equalTo(2));

    TrafficGraphEdge forward = graph.getOutgoingEdges("a").get(0);
    TrafficGraphEdge back = graph.getOtherEnd(forward);
    assertThat(back, equalTo(graph.getOutgoingEdges("d").get(0)));
    assertThat(graph.getMaxFailures(), equalTo(Integer.MAX_VALUE));
  }

  @Test
  public void testParseFailureModelMaxFailures() throws Exception {
    String json =
        "{\n"
            + "  \"failureModel\": {\"type\": \"UNDIRECTED_LINK\", \"maxFailures\": 1},\n"
            + "  \"flows\": [],\n"
            + "  \"links\": [\n"
            + "    {\"id\": \"a_d\",\n"
            + "     \"endpoint1\": {\"node\": \"a\", \"interface\": \"ge-0/0\"},\n"
            + "     \"endpoint2\": {\"node\": \"d\", \"interface\": \"ge-0/1\"},\n"
            + "     \"capacityGbps\": 95.0}\n"
            + "  ]\n"
            + "}";
    Path path = Files.createTempFile("traffic_k_test", ".json");
    Files.writeString(path, json);
    TrafficGraph graph = TrafficGraph.fromTrafficJson(path);
    assertThat(graph.getMaxFailures(), equalTo(1));
    assertThat(graph.getFailureVariables(), equalTo(java.util.Collections.singletonList("a_d")));
  }

  @Test
  public void testParseSrPolicyForwardingAlias() throws Exception {
    String json =
        "{\n"
            + "  \"flows\": [\n"
            + "    {\"id\": \"s-sr\", \"source\": \"s\", \"destination\": \"5.5.5.5/32\",\n"
            + "     \"demandGbps\": 80.0, \"forwarding\": \"SR_POLICY\", \"color\": 100,\n"
            + "     \"policy\": \"split-to-D\"}\n"
            + "  ],\n"
            + "  \"links\": [\n"
            + "    {\"id\": \"a_s\",\n"
            + "     \"endpoint1\": {\"node\": \"a\", \"interface\": \"ge-0/0\"},\n"
            + "     \"endpoint2\": {\"node\": \"s\", \"interface\": \"ge-0/1\"},\n"
            + "     \"capacityGbps\": 95.0}\n"
            + "  ]\n"
            + "}";
    Path path = Files.createTempFile("traffic_sr_test", ".json");
    Files.writeString(path, json);
    TrafficGraph graph = TrafficGraph.fromTrafficJson(path);
    assertThat(graph.getFlows().get(0).getForwarding(), equalTo(TrafficFlow.ForwardingType.SR_POLICY));
    assertThat(graph.getFlows().get(0).getColor(), equalTo(100));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testParseFromTrafficJsonRejectsDuplicateFlowId() throws Exception {
    String json =
        "{\n"
            + "  \"links\": [\n"
            + "    {\"id\": \"a_d\",\n"
            + "     \"endpoint1\": {\"node\": \"a\", \"interface\": \"ge-0/0\"},\n"
            + "     \"endpoint2\": {\"node\": \"d\", \"interface\": \"ge-0/1\"},\n"
            + "     \"capacityGbps\": 100.0}\n"
            + "  ],\n"
            + "  \"flows\": [\n"
            + "    {\"id\": \"f\", \"source\": \"a\", \"destination\": \"5.5.5.5/32\",\n"
            + "     \"demandGbps\": 20.0, \"forwarding\": \"IP\"},\n"
            + "    {\"id\": \"f\", \"source\": \"a\", \"destination\": \"6.6.6.6/32\",\n"
            + "     \"demandGbps\": 20.0, \"forwarding\": \"IP\"}\n"
            + "  ]\n"
            + "}";
    Path path = Files.createTempFile("traffic_graph_test_dup", ".json");
    Files.writeString(path, json);
    TrafficGraph.fromTrafficJson(path);
  }

  @Test(expected = IllegalArgumentException.class)
  public void testParseFromTrafficJsonRejectsUnknownForwardingType() throws Exception {
    String json =
        "{\n"
            + "  \"links\": [\n"
            + "    {\"id\": \"a_d\",\n"
            + "     \"endpoint1\": {\"node\": \"a\", \"interface\": \"ge-0/0\"},\n"
            + "     \"endpoint2\": {\"node\": \"d\", \"interface\": \"ge-0/1\"},\n"
            + "     \"capacityGbps\": 100.0}\n"
            + "  ],\n"
            + "  \"flows\": [\n"
            + "    {\"id\": \"f\", \"source\": \"a\", \"destination\": \"5.5.5.5/32\",\n"
            + "     \"demandGbps\": 20.0, \"forwarding\": \"UNKNOWN\"}\n"
            + "  ]\n"
            + "}";
    Path path = Files.createTempFile("traffic_graph_test_bad_forwarding", ".json");
    Files.writeString(path, json);
    TrafficGraph.fromTrafficJson(path);
  }
}
