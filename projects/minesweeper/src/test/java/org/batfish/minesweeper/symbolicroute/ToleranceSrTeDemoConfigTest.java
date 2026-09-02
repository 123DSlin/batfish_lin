package org.batfish.minesweeper.symbolicroute;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.io.IOException;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.answers.AnswerElement;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrPolicy;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.symbolicsr.GuardedSrCandidate;
import org.batfish.minesweeper.symbolicsr.GuardedSrPolicyDatabase;
import org.batfish.minesweeper.utils.RibPrinter;
import org.batfish.question.routes.RoutesAnswerer;
import org.batfish.question.routes.RoutesQuestion;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Parser-driven acceptance for the concrete-failure SR-TE tolerance demo configuration. */
@RunWith(JUnit4.class)
public final class ToleranceSrTeDemoConfigTest {
  private static final String SNAPSHOT = "networks/tolerance_sr_te_demo/configs/";
  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testParsedTopologyAndSrPolicy() throws IOException {
    SortedMap<String, byte[]> configurationBytes = new TreeMap<>();
    for (String filename : ImmutableList.of("A.cfg", "B.cfg", "D.cfg", "S.cfg", "X.cfg")) {
      configurationBytes.put(filename, Files.readAllBytes(Paths.get(SNAPSHOT + filename)));
    }
    Batfish batfish =
        BatfishTestUtils.getBatfishFromTestrigText(
            TestrigText.builder().setConfigurationBytes(configurationBytes).build(), _folder);
    SortedMap<String, Configuration> configurations =
        batfish.loadConfigurations(batfish.getSnapshot());

    assertThat(configurations.keySet().toString(), equalTo("[a, b, d, s, x]"));
    SegmentRoutingVrfConfig srVrf =
        configurations
            .get("s")
            .getSegmentRoutingConfig()
            .getVrfs()
            .get(Configuration.DEFAULT_VRF_NAME);
    assertThat(srVrf.getSegmentLists(), hasSize(2));
    assertThat(srVrf.getPolicies(), hasSize(1));
    SrPolicy policy = srVrf.getPolicies().get(0);
    assertThat(policy.getName(), equalTo("split-to-D"));
    assertThat(policy.getCandidates(), hasSize(2));
    assertThat(policy.getCandidates().get(0).getWeight(), equalTo(50L));
    assertThat(policy.getCandidates().get(1).getWeight(), equalTo(50L));

    batfish.computeDataPlane(batfish.getSnapshot());
    DataPlane dataPlane = batfish.loadDataPlane(batfish.getSnapshot());
    StringWriter concreteRibText = new StringWriter();
    AnswerElement concreteRoutes =
        new RoutesAnswerer(new RoutesQuestion(), batfish).answer(batfish.getSnapshot());
    RibPrinter.printRouteTable(concreteRoutes, new PrintWriter(concreteRibText));
    assertThat(
        countForwardingRows(concreteRibText.toString(), "b", "10.0.12.0/30", "d"),
        equalTo(1L));
    assertThat(
        countForwardingRows(concreteRibText.toString(), "s", "10.0.15.0/30", "a"),
        equalTo(1L));
    assertThat(
        countForwardingRows(concreteRibText.toString(), "s", "10.0.15.0/30", "b"),
        equalTo(1L));
    Set<AnnotatedRoute<AbstractRoute>> xRoutesToD =
        dataPlane
            .getRibs()
            .get("x")
            .get(Configuration.DEFAULT_VRF_NAME)
            .longestPrefixMatch(Ip.parse("5.5.5.5"));
    assertThat(xRoutesToD, hasSize(1));
    assertThat(
        xRoutesToD.iterator().next().getRoute().getNextHop(),
        equalTo(NextHopIp.of(Ip.parse("10.0.15.2"))));
    IsisTopology isisTopology =
        IsisTopology.initIsisTopology(configurations, synthesizeL3Topology(configurations));
    BatfishSymbolicRoutePipelineInput input =
        BatfishParsedSnapshotPipelineInputBuilder.build(
            configurations,
            dataPlane.getRibs(),
            batfish.getTopologyProvider().getBgpTopology(batfish.getSnapshot()).getGraph(),
            isisTopology,
            GUARDS);
    assertThat(input.getRedistributionRules(), hasSize(0));
    assertThat(
        input.getMainSeeds().stream()
            .filter(seed -> seed.getMessageId().startsWith("local:"))
            .count(),
        equalTo(12L));

    BatfishSymbolicRoutePipelineResult result = BatfishSymbolicRoutePipeline.run(input);
    RouteGuard allLinksUp =
        GUARDS
            .variable("a_s")
            .and(GUARDS.variable("a_x"))
            .and(GUARDS.variable("a_d"))
            .and(GUARDS.variable("b_s"))
            .and(GUARDS.variable("b_d"))
            .and(GUARDS.variable("d_x"));
    for (String router : configurations.keySet()) {
      Set<AbstractRoute> symbolicAllUp = new HashSet<>();
      GuardedRib<AnnotatedRoute<AbstractRoute>> rib = result.getMainRibNetwork().getRib(router);
      rib.getEntries()
          .forEach(
              candidate ->
                  rib.getContributionEntries(candidate.getSymbolicRoute().getKey())
                      .values()
                      .forEach(
                          branch -> {
                            if (branch.getSelectionGuard().and(allLinksUp).isSatisfiable()) {
                              symbolicAllUp.add(
                                  branch.getSymbolicRoute().getRoute().getAbstractRoute());
                            }
                          }));
      assertThat(
          symbolicAllUp,
          equalTo(dataPlane.getRibs().get(router).get(Configuration.DEFAULT_VRF_NAME).getRoutes()));
    }
    GuardedSrPolicyDatabase database = result.getGuardedSrPolicyDatabase();
    assertThat(database.getCandidates(), hasSize(2));
    assertThat(database.getContributions(), hasSize(2));
    GuardedSrCandidate upper = candidate(database, "explicit:upper-via-A");
    GuardedSrCandidate lower = candidate(database, "explicit:lower-via-B");
    assertThat(
        upper
            .getAvailabilityGuard()
            .isEquivalentTo(GUARDS.variable("a_s").and(GUARDS.variable("a_d"))),
        equalTo(true));
    assertThat(
        lower
            .getAvailabilityGuard()
            .isEquivalentTo(GUARDS.variable("b_s").and(GUARDS.variable("b_d"))),
        equalTo(true));
    ImmutableList<SymbolicRibRecord> sToD =
        result.getMainForwardingBranches().stream()
            .filter(
                route ->
                    route.getRouter().equals("s")
                        && route.getPrefix().equals("5.5.5.5/32")
                        && route.getProtocol().equals("ISIS_L2"))
            .collect(ImmutableList.toImmutableList());
    assertThat(sToD, hasSize(3));
    assertThat(
        sToD.stream()
            .map(SymbolicRibRecord::getForwardingPath)
            .collect(ImmutableList.toImmutableList()),
        containsInAnyOrder(
            ImmutableList.of("s", "a", "d"),
            ImmutableList.of("s", "a", "x", "d"),
            ImmutableList.of("s", "b", "d")));
    assertThat(
        sToD.stream()
            .anyMatch(
                route ->
                    route.getForwardingPath().equals(ImmutableList.of("s", "a", "d"))
                        && route.getSelectionGuard().contains("a_s")
                        && route.getSelectionGuard().contains("a_d")),
        equalTo(true));
    assertThat(
        sToD.stream()
            .anyMatch(
                route ->
                    route.getForwardingPath().equals(ImmutableList.of("s", "b", "d"))
                        && route.getSelectionGuard().contains("b_s")
                        && route.getSelectionGuard().contains("b_d")),
        equalTo(true));
    assertThat(
        sToD.stream()
            .anyMatch(
                route ->
                    route.getForwardingPath().equals(ImmutableList.of("s", "a", "x", "d"))
                        && route.getSelectionGuard().contains("a_s")
                        && route.getSelectionGuard().contains("a_x")
                        && route.getSelectionGuard().contains("d_x")
                        && route.getSelectionGuard().contains("not")),
        equalTo(true));
  }

  private static GuardedSrCandidate candidate(
      GuardedSrPolicyDatabase database, String candidateName) {
    return database.getCandidates().stream()
        .filter(candidate -> candidate.getKey().getCandidateName().equals(candidateName))
        .findFirst()
        .get();
  }

  private static long countForwardingRows(
      String output, String node, String prefix, String nextHop) {
    return Arrays.stream(output.split("\\R"))
        .map(String::trim)
        .map(line -> line.split("\\s+"))
        .filter(fields -> fields.length >= 7)
        .filter(fields -> fields[0].equals(node))
        .filter(fields -> fields[2].equals(prefix))
        .filter(fields -> fields[6].equals(nextHop))
        .count();
  }
}
