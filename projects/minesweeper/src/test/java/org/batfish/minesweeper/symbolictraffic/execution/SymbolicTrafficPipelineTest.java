package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Dual-engine JSON contract without running a Batfish snapshot. */
@RunWith(JUnit4.class)
public final class SymbolicTrafficPipelineTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Test
  public void testYuJsonNamesTheSymbolicEngine() {
    TrafficFlow flow =
        new TrafficFlow(
            "a-to-b",
            "a",
            Prefix.parse("5.5.5.5/32"),
            20.0,
            TrafficFlow.ForwardingType.IP,
            null,
            null);
    TrafficGraphEdge ab =
        new TrafficGraphEdge("a_b", "a", "b", "Ethernet0", "Ethernet0", 95.0, false);
    TrafficGraph graph =
        new TrafficGraph(
            Arrays.asList("a", "b"), Collections.singleton(ab), Collections.singleton(flow), 1);
    SymbolicTrafficLoad yu = new SymbolicTrafficExecution(graph).trafficLoads();
    Map<TrafficGraphEdge, Double> concrete = new HashMap<>();
    concrete.put(ab, 20.0);
    SymbolicTrafficPipeline.Result result = new SymbolicTrafficPipeline.Result(graph, yu, concrete);

    assertThat(result.toYuJson(), containsString(SymbolicTrafficPipeline.YU_SCHEMA));
    assertThat(result.toYuJson(), containsString("YU_ALGORITHM_1"));
    assertThat(result.toConcreteJson(), containsString(SymbolicTrafficPipeline.CONCRETE_SCHEMA));
    assertThat(result.toConcreteJson(), containsString("CONCRETE_DATAPLANE"));
    assertThat(result.getConcreteLoads().get(ab), equalTo(20.0));
  }

  @Test
  public void testExecutionTextNamesMatrixThenTau() {
    TrafficFlow flow =
        new TrafficFlow(
            "a-to-b",
            "a",
            Prefix.parse("5.5.5.5/32"),
            20.0,
            TrafficFlow.ForwardingType.IP,
            null,
            null);
    TrafficGraphEdge ab =
        new TrafficGraphEdge("a_b", "a", "b", "Ethernet0", "Ethernet0", 95.0, false);
    TrafficGraph graph =
        new TrafficGraph(
            Arrays.asList("a", "b"), Collections.singleton(ab), Collections.singleton(flow), 1);
    SymbolicTrafficExecution.TrafficSimulation simulation =
        new SymbolicTrafficExecution(graph).simulateAll();
    Map<TrafficGraphEdge, Double> concrete = new HashMap<>();
    concrete.put(ab, 20.0);
    SymbolicTrafficPipeline.Result result =
        new SymbolicTrafficPipeline.Result(
            graph, simulation.getLoads(), concrete, simulation.getMatrices());

    String text = result.toExecutionText();
    assertThat(text, containsString("M_f[l, S]"));
    assertThat(text, containsString("Per-flow link STF"));
    assertThat(text, containsString("τ_l"));
    assertThat(text, containsString("KREDUCE each iteration"));
    assertThat(text, containsString("a-to-b"));
  }

  @Test
  public void testExecutionTextPrintsGuardedSrPathShareEquation() {
    TrafficGraph graph =
        new TrafficGraph(Collections.singleton("s"), Collections.emptySet(), Collections.emptySet(), 1);
    SrPolicy.Path upper =
        new SrPolicy.Path(
            "upper-via-A", GUARDS.variable("a_s").and(GUARDS.variable("a_d")), 50,
            Collections.singletonList(SrPolicy.Segment.node("a")));
    SrPolicy.Path lower =
        new SrPolicy.Path(
            "lower-via-B", GUARDS.variable("b_s").and(GUARDS.variable("b_d")), 50,
            Collections.singletonList(SrPolicy.Segment.node("b")));
    SrPolicy policy =
        new SrPolicy(
            "s",
            Prefix.parse("5.5.5.5/32"),
            100,
            "split-to-D",
            null,
            Arrays.asList(upper, lower));
    SymbolicTrafficPipeline.Result result =
        new SymbolicTrafficPipeline.Result(
            graph,
            new SymbolicTrafficLoad(),
            Collections.emptyMap(),
            Collections.emptyMap(),
            Collections.singletonMap("s", Collections.singletonList(policy)));

    String text = result.toExecutionText();
    assertThat(text, containsString("SR policy path shares"));
    assertThat(text, containsString("Policy s/split-to-D"));
    assertThat(text, containsString("g_p = (a_d and a_s)"));
    assertThat(text, containsString("g_p = (b_d and b_s)"));
    assertThat(text, containsString("c_p = ((a_d and a_s) * 50)"));
  }
}
