package org.batfish.minesweeper.symbolicroute;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.GenericRibReadOnly;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.IsoAddress;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.Topology;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisInterfaceMode;
import org.batfish.datamodel.isis.IsisInterfaceSettings;
import org.batfish.datamodel.isis.IsisLevel;
import org.batfish.datamodel.isis.IsisLevelSettings;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.dataplane.rib.Rib;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Stage 6.2 tests for separate L1/L2 RIBs and guarded L1-to-L2 route upgrade. */
@RunWith(JUnit4.class)
public final class BatfishIsisLevel2PipelineTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix ORIGIN = Prefix.parse("1.1.1.1/32");

  @Test
  public void testL1ToL2UpgradeAttachBoundaryAndMainInstall() {
    Map<String, Configuration> configurations = configurations();
    Topology l3 = synthesizeL3Topology(configurations);
    IsisTopology topology = IsisTopology.initIsisTopology(configurations, l3);
    TopologyLinkGuards linkGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, GUARDS);
    BatfishIsisTopologyAdapter.Result isis =
        BatfishIsisTopologyAdapter.build(configurations, topology, linkGuards, GUARDS);

    assertThat(isis.getEdges(), hasSize(2));
    assertThat(isis.getL2Edges(), hasSize(4));

    BatfishSymbolicRoutePipelineResult result =
        BatfishSymbolicRoutePipeline.run(input(configurations, isis));
    List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> r4Origin =
        result.getIsisL2RibNetwork().getRib("r4").getEntries().stream()
            .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN))
            .collect(ImmutableList.toImmutableList());
    assertThat(r4Origin, hasSize(1));
    IsisRoute r4Route = r4Origin.get(0).getSymbolicRoute().getRoute().getRoute();
    assertThat(r4Route.getLevel(), equalTo(IsisLevel.LEVEL_2));
    assertThat(r4Route.getMetric(), equalTo(30L));
    RouteGuard expected =
        GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r3")).and(GUARDS.variable("r3_r4"));
    assertThat(r4Origin.get(0).getSelectionGuard().isEquivalentTo(expected), equalTo(true));

    assertThat(
        result.getMainRibNetwork().getRib("r4").getEntries().stream()
            .anyMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN)),
        equalTo(true));
    assertAttachedDefaultSemantics(result);
    assertThat(result.toReadableText().contains("IS-IS LEVEL-2 RIB"), equalTo(true));
  }

  @Test
  public void testIncrementalL1WithdrawalAndGuardUpdateReconcileL2() {
    Map<String, Configuration> configurations = configurations();
    IsisTopology topology =
        IsisTopology.initIsisTopology(configurations, synthesizeL3Topology(configurations));
    TopologyLinkGuards linkGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, GUARDS);
    BatfishIsisTopologyAdapter.Result isis =
        BatfishIsisTopologyAdapter.build(configurations, topology, linkGuards, GUARDS);
    BatfishSymbolicRoutePipelineResult result =
        BatfishSymbolicRoutePipeline.run(input(configurations, isis));
    BatfishIsisLevelTransitionReconciler reconciler = result.getIsisLevelTransitionReconciler();
    int initialTransitions = reconciler.getActiveTransitionCount();
    GuardedRibEntry<AnnotatedRoute<IsisRoute>> originEntry =
        result.getIsisL1RibNetwork().getRib("r1").getEntries().stream()
            .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN))
            .findFirst()
            .get();
    SymbolicRoute<AnnotatedRoute<IsisRoute>> origin = originEntry.getSymbolicRoute();
    String messageId = "isis-l1-origin:r1:default:Loopback0:1.1.1.1/32";
    SymbolicRouteContributionId originContribution =
        new SymbolicRouteContributionId(messageId, "r1", "r1");

    result.getIsisL1RibNetwork().getEngine().withdraw(ImmutableList.of(originContribution));

    assertThat(reconciler.getActiveTransitionCount() < initialTransitions, equalTo(true));
    assertThat(reconciler.getLastConvergence().getProcessedWithdrawals() > 0, equalTo(true));
    assertThat(hasRoute(result.getIsisL2RibNetwork(), "r4", ORIGIN), equalTo(false));

    RouteGuard firstGuard = GUARDS.variable("origin_enabled");
    result
        .getIsisL1RibNetwork()
        .getEngine()
        .converge(
            ImmutableList.of(
                localMessage(messageId, origin.getRoute(), firstGuard, origin.getProvenance())));
    RouteGuard pathGuard =
        GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r3")).and(GUARDS.variable("r3_r4"));
    assertThat(
        l2OriginAtR4(result).getSelectionGuard().isEquivalentTo(firstGuard.and(pathGuard)),
        equalTo(true));

    RouteGuard updatedGuard = GUARDS.variable("origin_updated");
    result
        .getIsisL1RibNetwork()
        .getEngine()
        .converge(
            ImmutableList.of(
                localMessage(messageId, origin.getRoute(), updatedGuard, origin.getProvenance())));
    assertThat(
        l2OriginAtR4(result).getSelectionGuard().isEquivalentTo(updatedGuard.and(pathGuard)),
        equalTo(true));

    AnnotatedRoute<IsisRoute> replacementRoute =
        new AnnotatedRoute<>(
            origin.getRoute().getRoute().toBuilder().setMetric(5L).build(), DEFAULT_VRF_NAME);
    result
        .getIsisL1RibNetwork()
        .getEngine()
        .replace(
            originContribution,
            localMessage(
                "isis-l1-origin-r1-loopback-replacement",
                replacementRoute,
                updatedGuard,
                origin.getProvenance()));
    assertThat(
        l2OriginAtR4(result).getSymbolicRoute().getRoute().getRoute().getMetric(), equalTo(35L));
    assertThat(
        l2OriginAtR4(result).getSelectionGuard().isEquivalentTo(updatedGuard.and(pathGuard)),
        equalTo(true));
  }

  private static SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> localMessage(
      String messageId,
      AnnotatedRoute<IsisRoute> route,
      RouteGuard guard,
      SymbolicRouteProvenance provenance) {
    return new SymbolicRouteMessage<>(
        messageId, "r1", "r1", SymbolicRouteMessage.Stage.INGRESS, route, guard, provenance);
  }

  private static boolean hasRoute(
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> network, String router, Prefix prefix) {
    return network.getRib(router).getEntries().stream()
        .anyMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(prefix));
  }

  private static GuardedRibEntry<AnnotatedRoute<IsisRoute>> l2OriginAtR4(
      BatfishSymbolicRoutePipelineResult result) {
    return result.getIsisL2RibNetwork().getRib("r4").getEntries().stream()
        .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN))
        .findFirst()
        .get();
  }

  @Test
  public void testL2ThreePreferenceTiersAndEcmp() {
    BatfishIsisProtocolAdapter adapter =
        new BatfishIsisProtocolAdapter(ImmutableList.of(), IsisLevel.LEVEL_2);
    GuardedRib<AnnotatedRoute<IsisRoute>> rib =
        new GuardedRib<>(adapter.preferenceComparator("r1"));
    RouteGuard high = GUARDS.variable("high");
    RouteGuard equalLeft = GUARDS.variable("equal_left");
    RouteGuard equalRight = GUARDS.variable("equal_right");
    RouteGuard low = GUARDS.variable("low");
    put(rib, "high", l2Route(10L, "10.0.0.1"), high);
    put(rib, "equal-left", l2Route(20L, "10.0.0.2"), equalLeft);
    put(rib, "equal-right", l2Route(20L, "10.0.0.3"), equalRight);
    put(rib, "low", l2Route(30L, "10.0.0.4"), low);

    List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> entries = rib.getEntries();
    assertThat(entries, hasSize(4));
    assertThat(
        entry(entries, 10L, "10.0.0.1").getSelectionGuard().isEquivalentTo(high), equalTo(true));
    RouteGuard middleSuppression = high.not();
    assertThat(
        entry(entries, 20L, "10.0.0.2")
            .getSelectionGuard()
            .isEquivalentTo(equalLeft.and(middleSuppression)),
        equalTo(true));
    assertThat(
        entry(entries, 20L, "10.0.0.3")
            .getSelectionGuard()
            .isEquivalentTo(equalRight.and(middleSuppression)),
        equalTo(true));
    assertThat(
        entry(entries, 30L, "10.0.0.4")
            .getSelectionGuard()
            .isEquivalentTo(low.and(high.not()).and(equalLeft.not()).and(equalRight.not())),
        equalTo(true));
  }

  @Test
  public void testUnsupportedOverloadFailsClosed() {
    NetworkFactory nf = new NetworkFactory();
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname("r1")
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    Vrf vrf = nf.vrfBuilder().setOwner(configuration).setName(DEFAULT_VRF_NAME).build();
    IsisProcess.builder()
        .setVrf(vrf)
        .setNetAddress(new IsoAddress("49.0001.0000.0000.0001.00"))
        .setLevel1(IsisLevelSettings.builder().build())
        .setOverload(true)
        .build();
    Map<String, Configuration> configurations = ImmutableMap.of("r1", configuration);
    assertThrows(
        IllegalArgumentException.class,
        () ->
            BatfishIsisTopologyAdapter.build(
                configurations,
                IsisTopology.EMPTY,
                BatfishTopologyGuardInitializer.inferTopology(configurations, GUARDS),
                GUARDS));
  }

  private static void assertThrows(Class<? extends Throwable> expected, Runnable action) {
    try {
      action.run();
      fail("Expected " + expected.getSimpleName());
    } catch (Throwable thrown) {
      if (!expected.isInstance(thrown)) {
        throw new AssertionError(
            "Expected " + expected.getSimpleName() + " but caught " + thrown, thrown);
      }
    }
  }

  private static void put(
      GuardedRib<AnnotatedRoute<IsisRoute>> rib,
      String id,
      AnnotatedRoute<IsisRoute> route,
      RouteGuard guard) {
    SymbolicRouteProvenance provenance =
        new SymbolicRouteProvenance("r1", "r1", null, null, ImmutableList.of("r1"), null);
    SymbolicRoute<AnnotatedRoute<IsisRoute>> symbolic =
        new SymbolicRoute<>(
            new SymbolicRouteKey("r1", DEFAULT_VRF_NAME, route), route, guard, provenance);
    rib.putContribution(new SymbolicRouteContributionId(id, "r1", "r1"), symbolic);
  }

  private static AnnotatedRoute<IsisRoute> l2Route(long metric, String nextHop) {
    IsisRoute route =
        IsisRoute.testBuilder()
            .setLevel(IsisLevel.LEVEL_2)
            .setProtocol(RoutingProtocol.ISIS_L2)
            .setMetric(metric)
            .setNetwork(Prefix.parse("192.0.2.0/24"))
            .setNextHopIp(Ip.parse(nextHop))
            .build();
    return new AnnotatedRoute<>(route, DEFAULT_VRF_NAME);
  }

  private static GuardedRibEntry<AnnotatedRoute<IsisRoute>> entry(
      List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> entries, long metric, String nextHop) {
    return entries.stream()
        .filter(
            candidate -> candidate.getSymbolicRoute().getRoute().getRoute().getMetric() == metric)
        .filter(
            candidate ->
                candidate
                    .getSymbolicRoute()
                    .getRoute()
                    .getRoute()
                    .getNextHopIp()
                    .equals(Ip.parse(nextHop)))
        .findFirst()
        .get();
  }

  private static void assertAttachedDefaultSemantics(BatfishSymbolicRoutePipelineResult result) {
    List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> r1Defaults =
        result.getIsisL1RibNetwork().getRib("r1").getEntries().stream()
            .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(Prefix.ZERO))
            .collect(ImmutableList.toImmutableList());
    assertThat(r1Defaults, hasSize(1));
    assertThat(
        r1Defaults.get(0).getSymbolicRoute().getRoute().getRoute().getAttach(), equalTo(true));
    assertThat(
        r1Defaults.get(0).getSelectionGuard().isEquivalentTo(GUARDS.variable("r1_r2")),
        equalTo(true));
    assertThat(
        result.getMainRibNetwork().getRib("r1").getEntries().stream()
            .anyMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(Prefix.ZERO)),
        equalTo(true));
    assertThat(
        result.getMainRibNetwork().getRib("r2").getEntries().stream()
            .noneMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(Prefix.ZERO)),
        equalTo(true));
    assertThat(
        result.getIsisL2RibNetwork().getRibs().values().stream()
            .flatMap(rib -> rib.getEntries().stream())
            .noneMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(Prefix.ZERO)),
        equalTo(true));
  }

  private static BatfishSymbolicRoutePipelineInput input(
      Map<String, Configuration> configurations, BatfishIsisTopologyAdapter.Result isis) {
    Map<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>> concreteRibs =
        new LinkedHashMap<>();
    configurations
        .keySet()
        .forEach(router -> concreteRibs.put(router, ImmutableMap.of(DEFAULT_VRF_NAME, new Rib())));
    return new BatfishSymbolicRoutePipelineInput(
        configurations,
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        isis.getEdges(),
        isis.getSessions(),
        isis.getSeeds(),
        isis.getL2Edges(),
        isis.getL2Sessions(),
        isis.getL2Seeds(),
        concreteRibs);
  }

  private static Map<String, Configuration> configurations() {
    NetworkFactory nf = new NetworkFactory();
    Map<String, Configuration> configurations = new LinkedHashMap<>();
    configurations.put("r1", router(nf, "r1", "49.0001.0000.0000.0001.00", true, false));
    configurations.put("r2", router(nf, "r2", "49.0001.0000.0000.0002.00", true, true));
    configurations.put("r3", router(nf, "r3", "49.0002.0000.0000.0003.00", false, true));
    configurations.put("r4", router(nf, "r4", "49.0002.0000.0000.0004.00", false, true));
    addInterface(nf, configurations.get("r1"), "Loopback0", "1.1.1.1/32", true, false, true);
    addInterface(nf, configurations.get("r1"), "Ethernet12", "10.0.12.1/30", true, false, false);
    addInterface(nf, configurations.get("r2"), "Ethernet21", "10.0.12.2/30", true, false, false);
    addInterface(nf, configurations.get("r2"), "Ethernet23", "10.0.23.1/30", false, true, false);
    addInterface(nf, configurations.get("r3"), "Ethernet32", "10.0.23.2/30", false, true, false);
    addInterface(nf, configurations.get("r3"), "Ethernet34", "10.0.34.1/30", false, true, false);
    addInterface(nf, configurations.get("r4"), "Ethernet43", "10.0.34.2/30", false, true, false);
    return ImmutableMap.copyOf(configurations);
  }

  private static Configuration router(
      NetworkFactory nf, String hostname, String net, boolean l1, boolean l2) {
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname(hostname)
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    Vrf vrf = nf.vrfBuilder().setOwner(configuration).setName(DEFAULT_VRF_NAME).build();
    IsisProcess.builder()
        .setVrf(vrf)
        .setNetAddress(new IsoAddress(net))
        .setLevel1(l1 ? IsisLevelSettings.builder().build() : null)
        .setLevel2(l2 ? IsisLevelSettings.builder().build() : null)
        .build();
    return configuration;
  }

  private static void addInterface(
      NetworkFactory nf,
      Configuration owner,
      String name,
      String address,
      boolean l1,
      boolean l2,
      boolean passive) {
    IsisInterfaceLevelSettings settings =
        IsisInterfaceLevelSettings.builder()
            .setCost(10L)
            .setMode(passive ? IsisInterfaceMode.PASSIVE : IsisInterfaceMode.ACTIVE)
            .build();
    IsisInterfaceSettings isis =
        IsisInterfaceSettings.builder()
            .setPointToPoint(true)
            .setLevel1(l1 ? settings : null)
            .setLevel2(l2 ? settings : null)
            .build();
    nf.interfaceBuilder()
        .setOwner(owner)
        .setVrf(owner.getDefaultVrf())
        .setName(name)
        .setAddress(ConcreteInterfaceAddress.parse(address))
        .setIsis(isis)
        .build();
  }
}
