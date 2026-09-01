package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.batfish.datamodel.RoutingProtocol.BGP;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Prefix;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/**
 * Parses and executes the tolerance paper's four-router snapshot through the Stage 4.5 pipeline.
 */
@RunWith(JUnit4.class)
public final class ToleranceFourRouterParsedPipelineTest {

  private static final String SNAPSHOT = "networks/tolerance-symbolic-route/configs/";
  private static final Prefix PREFIX = Prefix.parse("10.0.0.0/24");
  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testParsedSnapshotProducesPaperSymbolicRib() throws IOException {
    SortedMap<String, byte[]> configurationBytes = new TreeMap<>();
    for (String filename : ImmutableList.of("R1.cfg", "R2.cfg", "R3.cfg", "R4.cfg")) {
      configurationBytes.put(filename, Files.readAllBytes(Paths.get(SNAPSHOT + filename)));
    }
    Batfish batfish =
        BatfishTestUtils.getBatfishFromTestrigText(
            TestrigText.builder().setConfigurationBytes(configurationBytes).build(), _folder);
    SortedMap<String, Configuration> configurations =
        batfish.loadConfigurations(batfish.getSnapshot());

    assertThat(configurations.keySet().toString(), equalTo("[r1, r2, r3, r4]"));
    assertThat(
        configurations.get("r4").getRoutingPolicies().containsKey("R4_IN_FROM_R2"), equalTo(true));

    batfish.computeDataPlane(batfish.getSnapshot());
    org.batfish.datamodel.DataPlane dataPlane = batfish.loadDataPlane(batfish.getSnapshot());
    BatfishSymbolicRoutePipelineInput input =
        BatfishParsedSnapshotPipelineInputBuilder.build(
            configurations,
            dataPlane.getRibs(),
            batfish.getTopologyProvider().getBgpTopology(batfish.getSnapshot()).getGraph(),
            GUARDS);
    // Cisco normalization attaches one wrapper policy to each BGP process. Policies for routers
    // without configured redistribution reject every MAIN candidate.
    assertThat(input.getRedistributionRules(), hasSize(4));
    BatfishBgpRedistributionRule parsedRule =
        input.getRedistributionRules().stream()
            .filter(rule -> rule.getRouter().equals("r1"))
            .findFirst()
            .get();
    assertThat(parsedRule.getRouter(), equalTo("r1"));
    assertThat(parsedRule.getSourceVrf(), equalTo(DEFAULT_VRF_NAME));
    assertThat(parsedRule.getTargetVrf(), equalTo(DEFAULT_VRF_NAME));
    assertThat(
        parsedRule.getPolicyName(),
        equalTo(
            configurations
                .get("r1")
                .getDefaultVrf()
                .getBgpProcess()
                .getRedistributionPolicy()));
    assertCanonicalIdentity(batfish, input, "r1", "Ethernet12", "r2", "Ethernet21");
    assertCanonicalIdentity(batfish, input, "r1", "Ethernet13", "r3", "Ethernet31");
    assertCanonicalIdentity(batfish, input, "r1", "Ethernet14", "r4", "Ethernet41");
    assertCanonicalIdentity(batfish, input, "r2", "Ethernet24", "r4", "Ethernet42");
    assertCanonicalIdentity(batfish, input, "r3", "Ethernet34", "r4", "Ethernet43");

    BatfishSymbolicRoutePipelineResult result = BatfishSymbolicRoutePipeline.run(input);

    List<GuardedRibEntry<AnnotatedRoute<Bgpv4Route>>> r4Routes =
        result.getBgpRibNetwork().getRib("r4").getEntries();
    assertThat(r4Routes, hasSize(3));
    assertGuard(r4Routes, 200L, GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")));
    assertGuard(
        r4Routes,
        100L,
        GUARDS.variable("r1_r4").and(GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")).not()));
    assertGuard(
        r4Routes,
        50L,
        GUARDS
            .variable("r1_r3")
            .and(GUARDS.variable("r3_r4"))
            .and(GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")).not())
            .and(GUARDS.variable("r1_r4").not()));
    List<GuardedRibEntry<AnnotatedRoute<AbstractRoute>>> r4MainRoutes =
        result.getMainRibNetwork().getRib("r4").getEntries();
    assertMainBgpGuard(
        r4MainRoutes, 200L, GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")));
    assertMainBgpGuard(
        r4MainRoutes,
        100L,
        GUARDS
            .variable("r1_r4")
            .and(GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")).not()));
    assertMainBgpGuard(
        r4MainRoutes,
        50L,
        GUARDS
            .variable("r1_r3")
            .and(GUARDS.variable("r3_r4"))
            .and(GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4")).not())
            .and(GUARDS.variable("r1_r4").not()));
    assertThat(
        result.getAllRoutes().stream()
            .filter(route -> route.getPlane() == SymbolicRibRecord.Plane.BGP)
            .count(),
        equalTo(10L));
    assertThat(result.getRoutes("r4", DEFAULT_VRF_NAME), hasSize(9));
    assertThat(
        result.getAllRoutes().stream()
            .filter(
                route ->
                    route.getPlane() == SymbolicRibRecord.Plane.MAIN
                        && route.getRouter().equals("r4")
                        && route.getPrefix().equals(PREFIX.toString())
                        && route.getProtocol().equals(BGP.toString()))
            .count(),
        equalTo(3L));
    assertThat(
        result.getAllRoutes().stream()
            .filter(
                route ->
                    route.getPlane() == SymbolicRibRecord.Plane.BGP
                        && route.getRouter().equals("r1")
                        && route.getPrefix().equals(PREFIX.toString()))
            .findFirst()
            .get()
            .getNextHopIp(),
        equalTo("-"));
    assertThat(result.toJson().contains("\"r4\""), equalTo(true));
    String readableText = result.toReadableText();
    String rawReadableText = result.toRawReadableText();
    assertThat(readableText.contains("MAIN RIB (cross-protocol forwarding candidates)"), equalTo(true));
    assertThat(readableText.contains("BGP LOC-RIB (protocol detail)"), equalTo(true));
    assertThat(readableText.matches("(?s).*Protocol\\s+NextHop\\s+NextHopIP.*"), equalTo(true));
    assertThat(readableText.contains("Network            RIB"), equalTo(false));
    assertThat(readableText.contains("(let"), equalTo(false));
    assertThat(rawReadableText.contains("(let"), equalTo(true));
    assertThat(readableText.contains("r4       default"), equalTo(true));
    assertThat(readableText.contains("(and r1_r2 r2_r4)"), equalTo(true));
    result
        .getMainRibNetwork()
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            assertThat(
                                entry
                                    .getAvailabilityGuard()
                                    .isEquivalentTo(
                                        entry.getAvailabilityGuard().simplifyForDisplay()),
                                equalTo(true))));
    result
        .getBgpRibNetwork()
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            assertThat(
                                entry
                                    .getSelectionGuard()
                                    .isEquivalentTo(entry.getSelectionGuard().simplifyForDisplay()),
                                equalTo(true))));
    System.out.println("BEGIN_SYMBOLIC_RIB_TEXT");
    System.out.print(readableText);
    System.out.println("END_SYMBOLIC_RIB_TEXT");
  }

  private static void assertCanonicalIdentity(
      Batfish batfish,
      BatfishSymbolicRoutePipelineInput input,
      String firstRouter,
      String firstInterface,
      String secondRouter,
      String secondInterface) {
    LinkFailureKey expected = LinkFailureKey.of(firstRouter, secondRouter);
    SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>> connectedSeed =
        input.getMainSeeds().stream()
            .filter(
                seed ->
                    seed.getMessageId()
                        .startsWith("connected:" + firstRouter + ":" + firstInterface + ":"))
            .findFirst()
            .get();
    assertThat(connectedSeed.getLinkFailureKey(), equalTo(expected));
    SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>> reverseConnectedSeed =
        input.getMainSeeds().stream()
            .filter(
                seed ->
                    seed.getMessageId()
                        .startsWith("connected:" + secondRouter + ":" + secondInterface + ":"))
            .findFirst()
            .get();
    assertThat(reverseConnectedSeed.getLinkFailureKey(), equalTo(expected));
    SymbolicRouteSession session =
        input.getBgpSessions().stream()
            .filter(
                candidate ->
                    candidate.getSender().equals(firstRouter)
                        && candidate.getReceiver().equals(secondRouter))
            .findFirst()
            .get();
    assertThat(session.getLinkFailureKey(), equalTo(expected));
    SymbolicRouteSession reverseSession =
        input.getBgpSessions().stream()
            .filter(
                candidate ->
                    candidate.getSender().equals(secondRouter)
                        && candidate.getReceiver().equals(firstRouter))
            .findFirst()
            .get();
    assertThat(reverseSession.getLinkFailureKey(), equalTo(expected));

    org.batfish.minesweeper.Graph graph =
        new org.batfish.minesweeper.Graph(batfish, batfish.getSnapshot());
    org.batfish.minesweeper.GraphEdge forwardingEdge =
        graph.getAllEdges().stream()
            .filter(
                edge ->
                    edge.getRouter().equals(firstRouter)
                        && secondRouter.equals(edge.getPeer())
                        && edge.getStart().getName().equals(firstInterface)
                        && edge.getEnd().getName().equals(secondInterface))
            .findFirst()
            .get();
    assertThat(
        org.batfish.minesweeper.smt.MinesweeperLinkFailureKeys.fromGraphEdge(forwardingEdge).get(),
        equalTo(expected));
    org.batfish.minesweeper.GraphEdge reverseForwardingEdge =
        graph.getAllEdges().stream()
            .filter(
                edge ->
                    edge.getRouter().equals(secondRouter)
                        && firstRouter.equals(edge.getPeer())
                        && edge.getStart().getName().equals(secondInterface)
                        && edge.getEnd().getName().equals(firstInterface))
            .findFirst()
            .get();
    assertThat(
        org.batfish.minesweeper.smt.MinesweeperLinkFailureKeys.fromGraphEdge(reverseForwardingEdge)
            .get(),
        equalTo(expected));
  }

  private static void assertGuard(
      List<GuardedRibEntry<AnnotatedRoute<Bgpv4Route>>> entries,
      long localPreference,
      RouteGuard expectedSelection) {
    GuardedRibEntry<AnnotatedRoute<Bgpv4Route>> entry =
        entries.stream()
            .filter(
                candidate ->
                    candidate.getSymbolicRoute().getKey().getNetwork().equals(PREFIX)
                        && candidate.getSymbolicRoute().getRoute().getRoute().getLocalPreference()
                            == localPreference)
            .findFirst()
            .get();
    assertThat(entry.getSelectionGuard().isEquivalentTo(expectedSelection), equalTo(true));
  }

  private static void assertMainBgpGuard(
      List<GuardedRibEntry<AnnotatedRoute<AbstractRoute>>> entries,
      long localPreference,
      RouteGuard expectedSelection) {
    GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry =
        entries.stream()
            .filter(
                candidate ->
                    candidate.getSymbolicRoute().getKey().getNetwork().equals(PREFIX)
                        && candidate.getSymbolicRoute().getRoute().getRoute() instanceof Bgpv4Route
                        && ((Bgpv4Route) candidate.getSymbolicRoute().getRoute().getRoute())
                                .getLocalPreference()
                            == localPreference)
            .findFirst()
            .get();
    assertThat(entry.getSelectionGuard().isEquivalentTo(expectedSelection), equalTo(true));
  }
}
