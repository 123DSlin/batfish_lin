package org.batfish.minesweeper.symbolicroute;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.answers.AnswerElement;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.utils.RibPrinter;
import org.batfish.question.routes.RoutesAnswerer;
import org.batfish.question.routes.RoutesQuestion;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Concrete-oracle validation for every zero/single-link failure in {@code traffic_demo}. */
@RunWith(JUnit4.class)
public final class TrafficDemoSingleLinkFailureTest {
  private static final String NETWORKS = "networks/";
  private static final ImmutableList<String> CONFIG_FILES =
      ImmutableList.of("r1.cfg", "r2.cfg", "r3.cfg", "r4.cfg");
  private static final ImmutableList<LinkFailureKey> LINKS =
      ImmutableList.of(
          LinkFailureKey.of("r1", "r2"),
          LinkFailureKey.of("r1", "r3"),
          LinkFailureKey.of("r1", "r4"),
          LinkFailureKey.of("r2", "r3"),
          LinkFailureKey.of("r3", "r4"));
  private static final ImmutableList<FailureScenario> SCENARIOS =
      ImmutableList.of(
          new FailureScenario("all_links_up", "traffic_demo", null, ImmutableMap.of()),
          new FailureScenario(
              "r1_r2_down",
              "traffic_demo_1_r1_r2",
              LinkFailureKey.of("r1", "r2"),
              ImmutableMap.of("r1", "GigabitEthernet0/0", "r2", "GigabitEthernet0/0")),
          new FailureScenario(
              "r1_r3_down",
              "traffic_demo_1_r1_r3",
              LinkFailureKey.of("r1", "r3"),
              ImmutableMap.of("r1", "GigabitEthernet1/0", "r3", "GigabitEthernet0/0")),
          new FailureScenario(
              "r1_r4_down",
              "traffic_demo_1_r1_r4",
              LinkFailureKey.of("r1", "r4"),
              ImmutableMap.of("r1", "GigabitEthernet2/0", "r4", "GigabitEthernet0/0")),
          new FailureScenario(
              "r2_r3_down",
              "traffic_demo_1_r2_r3",
              LinkFailureKey.of("r2", "r3"),
              ImmutableMap.of("r2", "GigabitEthernet1/0", "r3", "GigabitEthernet1/0")),
          new FailureScenario(
              "r3_r4_down",
              "traffic_demo_1_r3_r4",
              LinkFailureKey.of("r3", "r4"),
              ImmutableMap.of("r3", "GigabitEthernet2/0", "r4", "GigabitEthernet1/0")));

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testEveryZeroAndSingleLinkFailureAgainstConcreteDataplane() throws IOException {
    try (Context context = new Context()) {
      Z3RouteGuardFactory guards = new Z3RouteGuardFactory(context);
      Snapshot base = loadSnapshot("traffic_demo");
      BatfishSymbolicRoutePipelineResult symbolic = runSymbolicPipeline(base, guards);

      for (FailureScenario scenario : SCENARIOS) {
        Snapshot concrete =
            scenario._directory.equals("traffic_demo") ? base : loadSnapshot(scenario._directory);
        assertFailedInterfacesInactive(scenario, concrete._configurations);
        RouteGuard assignment = exactAssignment(guards, scenario._failedLink);
        Map<String, Set<AbstractRoute>> selected = selectedMainRoutes(symbolic, assignment);

        for (String router : concrete._configurations.keySet()) {
          Set<AbstractRoute> expected =
              concrete._dataPlane.getRibs().get(router).get(DEFAULT_VRF_NAME).getRoutes();
          assertThat(
              scenario._name + " concrete/symbolic MAIN mismatch at " + router,
              selected.get(router),
              equalTo(expected));
        }
        writeValidationArtifacts(scenario, concrete, selected);
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

  private static BatfishSymbolicRoutePipelineResult runSymbolicPipeline(
      Snapshot snapshot, Z3RouteGuardFactory guards) {
    IsisTopology isisTopology =
        IsisTopology.initIsisTopology(
            snapshot._configurations, synthesizeL3Topology(snapshot._configurations));
    return BatfishSymbolicRoutePipeline.run(
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
  }

  private static RouteGuard exactAssignment(Z3RouteGuardFactory guards, LinkFailureKey failedLink) {
    RouteGuard assignment = guards.trueGuard();
    for (LinkFailureKey link : LINKS) {
      RouteGuard value = guards.variable(link.guardName());
      assignment = assignment.and(link.equals(failedLink) ? value.not() : value);
    }
    return assignment;
  }

  private static Map<String, Set<AbstractRoute>> selectedMainRoutes(
      BatfishSymbolicRoutePipelineResult result, RouteGuard assignment) {
    Map<String, Set<AbstractRoute>> selected = new TreeMap<>();
    result
        .getMainRibNetwork()
        .getRibs()
        .forEach(
            (router, rib) -> {
              Set<AbstractRoute> routes = new HashSet<>();
              rib.getEntries()
                  .forEach(
                      candidate ->
                          rib.getContributionEntries(candidate.getSymbolicRoute().getKey())
                              .values()
                              .forEach(
                                  contribution -> {
                                    if (contribution
                                        .getSelectionGuard()
                                        .and(assignment)
                                        .isSatisfiable()) {
                                      routes.add(
                                          contribution
                                              .getSymbolicRoute()
                                              .getRoute()
                                              .getAbstractRoute());
                                    }
                                  }));
              selected.put(router, routes);
            });
    return selected;
  }

  private static void assertFailedInterfacesInactive(
      FailureScenario scenario, Map<String, Configuration> configurations) {
    scenario._failedInterfaces.forEach(
        (router, iface) ->
            assertThat(
                scenario._name + " must administratively disable " + router + ":" + iface,
                configurations.get(router).getAllInterfaces().get(iface).getActive(),
                equalTo(false)));
  }

  private static void writeValidationArtifacts(
      FailureScenario scenario, Snapshot concrete, Map<String, Set<AbstractRoute>> selected)
      throws IOException {
    String outputRoot = System.getenv("TEST_UNDECLARED_OUTPUTS_DIR");
    if (outputRoot == null) {
      return;
    }
    Path outputDirectory = Paths.get(outputRoot, "traffic_demo_failure_validation", scenario._name);
    Files.createDirectories(outputDirectory);
    AnswerElement routes =
        new RoutesAnswerer(new RoutesQuestion(), concrete._batfish)
            .answer(concrete._batfish.getSnapshot());
    try (PrintWriter writer =
        new PrintWriter(
            Files.newBufferedWriter(
                outputDirectory.resolve("0_data_plane.txt"), StandardCharsets.UTF_8))) {
      RibPrinter.printRouteTable(routes, writer);
    }
    List<String> symbolicRows = new ArrayList<>();
    selected.forEach(
        (router, routerRoutes) ->
            routerRoutes.forEach(
                route ->
                    symbolicRows.add(
                        String.format(
                            "%s %-18s %-10s %-5d %-5d %s",
                            router,
                            route.getNetwork(),
                            route.getProtocol(),
                            route.getMetric(),
                            route.getAdministrativeCost(),
                            route.getNextHop()))));
    symbolicRows.sort(String::compareTo);
    Files.write(
        outputDirectory.resolve("0_symbolic_selected.txt"), symbolicRows, StandardCharsets.UTF_8);
    Files.write(
        outputDirectory.resolve("0_comparison.txt"),
        ImmutableList.of(
            "scenario=" + scenario._name,
            "failedLink=" + (scenario._failedLink == null ? "none" : scenario._failedLink),
            "result=PASS",
            "comparison=all nodes, default VRF, complete MAIN route sets"),
        StandardCharsets.UTF_8);
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

  private static final class FailureScenario {
    private final String _name;
    private final String _directory;
    private final LinkFailureKey _failedLink;
    private final ImmutableMap<String, String> _failedInterfaces;

    private FailureScenario(
        String name,
        String directory,
        LinkFailureKey failedLink,
        ImmutableMap<String, String> failedInterfaces) {
      _name = name;
      _directory = directory;
      _failedLink = failedLink;
      _failedInterfaces = failedInterfaces;
    }
  }
}
