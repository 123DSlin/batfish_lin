package org.batfish.minesweeper.symbolictraffic.execution;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.containsString;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.symbolicroute.BatfishParsedSnapshotPipelineInputBuilder;
import org.batfish.minesweeper.symbolicroute.BatfishSymbolicRoutePipeline;
import org.batfish.minesweeper.symbolicroute.BatfishSymbolicRoutePipelineResult;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Parsed-snapshot specialization oracle for symbolic traffic under all zero/one-link failures. */
@RunWith(JUnit4.class)
public final class SymbolicTrafficEndToEndTest {

  private static final String NETWORKS = "networks/";
  private static final ImmutableList<String> CONFIG_FILES =
      ImmutableList.of("A.cfg", "B.cfg", "D.cfg", "S.cfg", "X.cfg");
  private static final ImmutableList<String> FAILURE_VARIABLES =
      ImmutableList.of("a_d", "a_s", "a_x", "b_d", "b_s", "d_x");
  private static final ImmutableMap<String, String> SCENARIOS =
      ImmutableMap.<String, String>builder()
          .put("tolerance_sr_te_demo", "")
          .put("tolerance_sr_te_demo_1_a_d", "a_d")
          .put("tolerance_sr_te_demo_1_a_s", "a_s")
          .put("tolerance_sr_te_demo_1_a_x", "a_x")
          .put("tolerance_sr_te_demo_1_b_d", "b_d")
          .put("tolerance_sr_te_demo_1_b_s", "b_s")
          .put("tolerance_sr_te_demo_1_d_x", "d_x")
          .build();

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testSymbolicLoadsMatchEveryParsedZeroOrOneLinkFailure() throws IOException {
    TrafficGraph graph =
        TrafficGraph.fromTrafficJson(Paths.get(NETWORKS, "tolerance_sr_te_demo", "traffic.json"));
    try (Context context = new Context()) {
      Snapshot base = loadSnapshot("tolerance_sr_te_demo");
      SymbolicTrafficPipeline.Result symbolic =
          runTrafficPipeline(graph, base, new Z3RouteGuardFactory(context));

      String smt = symbolic.toTrafficSmt();
      String outputs = System.getenv("TEST_UNDECLARED_OUTPUTS_DIR");
      if (outputs != null) {
        Files.write(
            Paths.get(outputs, TrafficSmtEncoder.SMT_FILE_NAME),
            smt.getBytes(StandardCharsets.UTF_8));
        Files.write(
            Paths.get(outputs, "symbolic_traffic_execution.txt"),
            symbolic.toExecutionText().getBytes(StandardCharsets.UTF_8));
      }
      assertThat(smt, containsString("(declare-fun a_d () Bool)"));
      assertThat(
          smt, containsString("Config_s_SrPolicy_split_to_D_Path_explicit_upper_via_A_weight"));
      assertThat(smt, containsString("(assert (<= (+"));

      for (Map.Entry<String, String> scenario : SCENARIOS.entrySet()) {
        Snapshot concrete =
            scenario.getKey().equals("tolerance_sr_te_demo")
                ? base
                : loadSnapshot(scenario.getKey());
        SymbolicTrafficPipeline.Result oracle =
            runTrafficPipeline(graph, concrete, new Z3RouteGuardFactory(context));
        Map<String, Boolean> assignment = assignment(scenario.getValue());
        for (TrafficGraphEdge edge : graph.getEdges()) {
          if (edge.isPseudoIncoming()) {
            continue;
          }
          double expected = oracle.getYuLoads().get(edge).evaluateAllUp();
          double actual = symbolic.getYuLoads().get(edge).evaluate(assignment);
          assertThat(scenario.getKey() + " " + edge, actual, closeTo(expected, 1e-9));
          if (scenario.getValue().isEmpty()) {
            assertThat(
                "all-up concrete oracle " + edge,
                actual,
                closeTo(oracle.getConcreteLoads().getOrDefault(edge, 0.0), 1e-9));
          }
        }
      }
    }
  }

  private Snapshot loadSnapshot(String directory) throws IOException {
    SortedMap<String, byte[]> configurationBytes = new TreeMap<>();
    for (String filename : CONFIG_FILES) {
      configurationBytes.put(
          filename, Files.readAllBytes(Paths.get(NETWORKS, directory, "configs", filename)));
    }
    Batfish batfish =
        BatfishTestUtils.getBatfishFromTestrigText(
            TestrigText.builder().setConfigurationBytes(configurationBytes).build(), _folder);
    SortedMap<String, Configuration> configurations =
        batfish.loadConfigurations(batfish.getSnapshot());
    batfish.computeDataPlane(batfish.getSnapshot());
    return new Snapshot(batfish, configurations, batfish.loadDataPlane(batfish.getSnapshot()));
  }

  private static SymbolicTrafficPipeline.Result runTrafficPipeline(
      TrafficGraph graph, Snapshot snapshot, Z3RouteGuardFactory guards) {
    IsisTopology isisTopology =
        IsisTopology.initIsisTopology(
            snapshot._configurations, synthesizeL3Topology(snapshot._configurations));
    BatfishSymbolicRoutePipelineResult controlPlane =
        BatfishSymbolicRoutePipeline.run(
            BatfishParsedSnapshotPipelineInputBuilder.build(
                snapshot._configurations,
                snapshot._dataPlane.getRibs(),
                snapshot
                    ._batfish
                    .getTopologyProvider()
                    .getBgpTopology(snapshot._batfish.getSnapshot())
                    .getGraph(),
                isisTopology,
                guards));
    return SymbolicTrafficPipeline.run(
        graph, controlPlane, snapshot._configurations, snapshot._dataPlane);
  }

  private static Map<String, Boolean> assignment(String failed) {
    Map<String, Boolean> assignment = new LinkedHashMap<>();
    for (String variable : FAILURE_VARIABLES) {
      assignment.put(variable, !variable.equals(failed));
    }
    return assignment;
  }

  private static final class Snapshot {
    private final Batfish _batfish;
    private final SortedMap<String, Configuration> _configurations;
    private final DataPlane _dataPlane;

    private Snapshot(
        Batfish batfish, SortedMap<String, Configuration> configurations, DataPlane dataPlane) {
      _batfish = batfish;
      _configurations = configurations;
      _dataPlane = dataPlane;
    }
  }
}
