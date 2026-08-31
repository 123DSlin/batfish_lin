package org.batfish.minesweeper.symbolicroute;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

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
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.IsoAddress;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.Topology;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisInterfaceMode;
import org.batfish.datamodel.isis.IsisInterfaceSettings;
import org.batfish.datamodel.isis.IsisLevelSettings;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrGlobalBlock;
import org.batfish.datamodel.sr.SrLabelRange;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.dataplane.rib.Rib;
import org.batfish.minesweeper.symbolicsr.GuardedSidEntry;
import org.batfish.minesweeper.symbolicsr.GuardedSidUpdate;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** End-to-end tests for the HoYAN Algorithm 2 Level-1 weighted propagation core. */
@RunWith(JUnit4.class)
public final class BatfishIsisAlgorithm2Test {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix ORIGIN_PREFIX = Prefix.parse("1.1.1.1/32");

  @Test
  public void testThreeMetricTiersEcmpAndFailureFallback() {
    Map<String, Configuration> configurations = diamondConfigurations();
    Topology l3 = synthesizeL3Topology(configurations);
    IsisTopology topology = IsisTopology.initIsisTopology(configurations, l3);
    TopologyLinkGuards linkGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, GUARDS);
    BatfishIsisTopologyAdapter.Result input =
        BatfishIsisTopologyAdapter.build(configurations, topology, linkGuards, GUARDS);

    assertThat(input.getEdges(), hasSize(14));
    for (BatfishIsisEdge edge : input.getEdges()) {
      SymbolicRouteSession session =
          input.getSessions().stream()
              .filter(candidate -> candidate.getSessionId().equals(edge.getSessionId()))
              .findFirst()
              .get();
      LinkFailureKey expected =
          linkGuards.getKey(
              edge.getSenderConfiguration().getHostname(), edge.getSenderInterface().getName());
      assertThat(session.getLinkFailureKey(), equalTo(expected));
    }

    SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> network =
        SymbolicRouteNetworkFactory.create(
            configurations.keySet(),
            input.getSessions(),
            input.getSeeds(),
            new BatfishIsisProtocolAdapter(input.getEdges()));
    network.converge();

    GuardedRibEntry<AnnotatedRoute<IsisRoute>> activeInterfaceOrigin =
        network.getRib("r1").getEntries().stream()
            .filter(
                entry ->
                    entry
                        .getSymbolicRoute()
                        .getKey()
                        .getNetwork()
                        .equals(Prefix.parse("10.0.12.0/30")))
            .filter(entry -> entry.getSymbolicRoute().getRoute().getRoute().getMetric() == 10L)
            .findFirst()
            .get();
    assertThat(
        activeInterfaceOrigin.getAvailabilityGuard().isEquivalentTo(GUARDS.variable("r1_r2")),
        equalTo(true));

    List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> routes =
        network.getRib("r4").getEntries().stream()
            .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN_PREFIX))
            .collect(ImmutableList.toImmutableList());
    assertThat(routes, hasSize(4));

    GuardedRibEntry<AnnotatedRoute<IsisRoute>> viaR2 = routeWithMetric(routes, 20L);
    List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> metric30 =
        routes.stream()
            .filter(entry -> entry.getSymbolicRoute().getRoute().getRoute().getMetric() == 30L)
            .collect(ImmutableList.toImmutableList());
    assertThat(metric30, hasSize(2));
    RouteGuard bestAvailability = GUARDS.variable("r1_r2").and(GUARDS.variable("r2_r4"));
    assertThat(viaR2.getAvailabilityGuard().isEquivalentTo(bestAvailability), equalTo(true));
    RouteGuard metric30Availability = GUARDS.falseGuard();
    for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> fallback : metric30) {
      metric30Availability = metric30Availability.or(fallback.getAvailabilityGuard());
      assertThat(
          fallback
              .getSelectionGuard()
              .isEquivalentTo(fallback.getAvailabilityGuard().and(bestAvailability.not())),
          equalTo(true));
    }
    GuardedRibEntry<AnnotatedRoute<IsisRoute>> metric40 = routeWithMetric(routes, 40L);
    assertThat(
        metric40
            .getSelectionGuard()
            .isEquivalentTo(
                metric40
                    .getAvailabilityGuard()
                    .and(bestAvailability.not())
                    .and(metric30Availability.not())),
        equalTo(true));

    network
        .getEngine()
        .withdraw(
            ImmutableList.of(
                new SymbolicRouteContributionId(
                    "isis-l1-origin:r1:default:Loopback0:1.1.1.1/32", "r1", "r1")));
    for (GuardedRib<AnnotatedRoute<IsisRoute>> rib : network.getRibs().values()) {
      assertThat(
          rib.getEntries().stream()
              .noneMatch(
                  entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN_PREFIX)),
          equalTo(true));
    }
  }

  @Test
  public void testPipelineInstallsIsisInMainAndReportsProtocolPlane() {
    Map<String, Configuration> configurations = diamondConfigurations();
    Topology l3 = synthesizeL3Topology(configurations);
    IsisTopology topology = IsisTopology.initIsisTopology(configurations, l3);
    TopologyLinkGuards linkGuards =
        BatfishTopologyGuardInitializer.inferTopology(configurations, GUARDS);
    BatfishIsisTopologyAdapter.Result isis =
        BatfishIsisTopologyAdapter.build(configurations, topology, linkGuards, GUARDS);
    Map<
            String,
            Map<String, org.batfish.datamodel.GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
        concreteRibs = new LinkedHashMap<>();
    configurations
        .keySet()
        .forEach(router -> concreteRibs.put(router, ImmutableMap.of(DEFAULT_VRF_NAME, new Rib())));
    BatfishSymbolicRoutePipelineInput input =
        new BatfishSymbolicRoutePipelineInput(
            configurations,
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            isis.getEdges(),
            isis.getSessions(),
            isis.getSeeds(),
            concreteRibs);

    BatfishSymbolicRoutePipelineResult result = BatfishSymbolicRoutePipeline.run(input);

    long isisCandidates =
        result.getAllRoutes().stream()
            .filter(record -> record.getRouter().equals("r4"))
            .filter(record -> record.getPrefix().equals(ORIGIN_PREFIX.toString()))
            .filter(record -> record.getPlane() == SymbolicRibRecord.Plane.ISIS_L1)
            .count();
    long mainCandidates =
        result.getAllRoutes().stream()
            .filter(record -> record.getRouter().equals("r4"))
            .filter(record -> record.getPrefix().equals(ORIGIN_PREFIX.toString()))
            .filter(record -> record.getPlane() == SymbolicRibRecord.Plane.MAIN)
            .count();
    assertThat(isisCandidates, equalTo(4L));
    assertThat(mainCandidates, equalTo(4L));
    assertThat(result.toReadableText().contains("IS-IS LEVEL-1 RIB"), equalTo(true));

    List<GuardedSidEntry> r4Sids =
        result.getGuardedSidDatabase().getEntries("r4", DEFAULT_VRF_NAME);
    assertThat(r4Sids, hasSize(2));
    GuardedSidEntry prefixSid = sidOfType(r4Sids, SrSidBindingKey.Type.PREFIX);
    GuardedSidEntry adjacencySid = sidOfType(r4Sids, SrSidBindingKey.Type.ADJACENCY);
    assertThat(prefixSid.getBinding().getSid(), equalTo(SrSidValue.mplsIndex(7L)));
    assertThat(
        adjacencySid.getAvailabilityGuard().isEquivalentTo(GUARDS.variable("r1_r2")),
        equalTo(true));
    assertThat(adjacencySid.getLinkFailureDependency(), equalTo(LinkFailureKey.of("r1", "r2")));
    RouteGuard expectedSidGuard = GUARDS.falseGuard();
    for (GuardedRibEntry<AnnotatedRoute<IsisRoute>> route :
        result.getIsisL1RibNetwork().getRib("r4").getEntries()) {
      if (route.getSymbolicRoute().getKey().getNetwork().equals(ORIGIN_PREFIX)) {
        expectedSidGuard = expectedSidGuard.or(route.getSelectionGuard());
      }
    }
    assertThat(prefixSid.getAvailabilityGuard().isEquivalentTo(expectedSidGuard), equalTo(true));

    result
        .getIsisL1RibNetwork()
        .getEngine()
        .withdraw(
            ImmutableList.of(
                new SymbolicRouteContributionId(
                    "isis-l1-origin:r1:default:Loopback0:1.1.1.1/32", "r1", "r1")));
    assertThat(result.getGuardedSidDatabase().getEntries("r4", DEFAULT_VRF_NAME), hasSize(1));
    assertThat(result.getGuardedSidReconciler().getLastDelta().getUpdates(), hasSize(5));
    assertThat(
        result.getGuardedSidReconciler().getLastDelta().getUpdates().stream()
            .allMatch(update -> update.getType() == GuardedSidUpdate.Type.REMOVED),
        equalTo(true));

    SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> origin =
        isis.getSeeds().stream()
            .filter(seed -> seed.getMessageId().contains("Loopback0:1.1.1.1/32"))
            .findFirst()
            .get()
            .toMessage();
    result
        .getIsisL1RibNetwork()
        .getEngine()
        .converge(ImmutableList.of(withGuard(origin, GUARDS.variable("sid_restore"))));
    assertThat(result.getGuardedSidDatabase().getEntries("r4", DEFAULT_VRF_NAME), hasSize(2));
    assertThat(
        result.getGuardedSidReconciler().getLastDelta().getUpdates().stream()
            .allMatch(update -> update.getType() == GuardedSidUpdate.Type.ADDED),
        equalTo(true));

    result
        .getIsisL1RibNetwork()
        .getEngine()
        .converge(ImmutableList.of(withGuard(origin, GUARDS.variable("sid_updated"))));
    assertThat(
        result.getGuardedSidReconciler().getLastDelta().getUpdates().stream()
            .allMatch(update -> update.getType() == GuardedSidUpdate.Type.GUARD_CHANGED),
        equalTo(true));

    attachPrefixSid(configurations.get("r1"), 8L);
    result.getGuardedSidReconciler().reconcile();
    assertThat(
        result.getGuardedSidReconciler().getLastDelta().getUpdates().stream()
            .allMatch(update -> update.getType() == GuardedSidUpdate.Type.REPLACED),
        equalTo(true));
    assertThat(
        result.getGuardedSidDatabase().getEntries("r4", DEFAULT_VRF_NAME).stream()
            .filter(entry -> entry.getBinding().getKey().getType() == SrSidBindingKey.Type.PREFIX)
            .findFirst()
            .get()
            .getBinding()
            .getSid(),
        equalTo(SrSidValue.mplsIndex(8L)));
  }

  private static GuardedSidEntry sidOfType(
      List<GuardedSidEntry> entries, SrSidBindingKey.Type type) {
    return entries.stream()
        .filter(entry -> entry.getBinding().getKey().getType() == type)
        .findFirst()
        .get();
  }

  private static SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> withGuard(
      SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> message, RouteGuard guard) {
    return new SymbolicRouteMessage<>(
        message.getMessageId(),
        message.getSender(),
        message.getReceiver(),
        message.getStage(),
        message.getRoute(),
        guard,
        message.getProvenance());
  }

  private static GuardedRibEntry<AnnotatedRoute<IsisRoute>> routeWithMetric(
      List<GuardedRibEntry<AnnotatedRoute<IsisRoute>>> routes, long metric) {
    return routes.stream()
        .filter(entry -> entry.getSymbolicRoute().getRoute().getRoute().getMetric() == metric)
        .findFirst()
        .get();
  }

  private static Map<String, Configuration> diamondConfigurations() {
    NetworkFactory nf = new NetworkFactory();
    Map<String, Configuration> configurations = new LinkedHashMap<>();
    for (int i = 1; i <= 5; i++) {
      String hostname = "r" + i;
      Configuration configuration =
          nf.configurationBuilder()
              .setHostname(hostname)
              .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
              .build();
      Vrf vrf = nf.vrfBuilder().setOwner(configuration).setName(DEFAULT_VRF_NAME).build();
      IsisProcess.builder()
          .setVrf(vrf)
          .setNetAddress(new IsoAddress(String.format("49.0001.0000.0000.000%d.00", i)))
          .setLevel1(IsisLevelSettings.builder().build())
          .build();
      configurations.put(hostname, configuration);
    }
    addInterface(nf, configurations.get("r1"), "Loopback0", "1.1.1.1/32", 0L, true);
    attachPrefixSid(configurations.get("r1"), 7L);
    addLink(
        nf,
        configurations,
        "r1",
        "Ethernet12",
        "10.0.12.1/30",
        10L,
        "r2",
        "Ethernet21",
        "10.0.12.2/30",
        10L);
    addLink(
        nf,
        configurations,
        "r2",
        "Ethernet24",
        "10.0.24.1/30",
        10L,
        "r4",
        "Ethernet42",
        "10.0.24.2/30",
        10L);
    addLink(
        nf,
        configurations,
        "r1",
        "Ethernet13",
        "10.0.13.1/30",
        15L,
        "r3",
        "Ethernet31",
        "10.0.13.2/30",
        15L);
    addLink(
        nf,
        configurations,
        "r3",
        "Ethernet34",
        "10.0.34.1/30",
        15L,
        "r4",
        "Ethernet43",
        "10.0.34.2/30",
        15L);
    addLink(
        nf,
        configurations,
        "r1",
        "Ethernet14",
        "10.0.14.1/30",
        30L,
        "r4",
        "Ethernet41",
        "10.0.14.2/30",
        30L);
    addLink(
        nf,
        configurations,
        "r1",
        "Ethernet15",
        "10.0.15.1/30",
        20L,
        "r5",
        "Ethernet51",
        "10.0.15.2/30",
        20L);
    addLink(
        nf,
        configurations,
        "r5",
        "Ethernet54",
        "10.0.54.1/30",
        20L,
        "r4",
        "Ethernet45",
        "10.0.54.2/30",
        20L);
    return ImmutableMap.copyOf(configurations);
  }

  private static void attachPrefixSid(Configuration owner, long index) {
    SrSidBinding binding =
        new SrSidBinding(
            new SrSidBindingKey(
                owner.getHostname(),
                DEFAULT_VRF_NAME,
                SrSidBindingKey.Type.PREFIX,
                0,
                SrPrefix.ipv4(ORIGIN_PREFIX),
                null,
                null),
            SrSidValue.mplsIndex(index),
            com.google.common.collect.ImmutableSet.of());
    SrSidBinding adjacency =
        new SrSidBinding(
            new SrSidBindingKey(
                owner.getHostname(),
                DEFAULT_VRF_NAME,
                SrSidBindingKey.Type.ADJACENCY,
                0,
                null,
                "Ethernet12",
                null),
            SrSidValue.mplsIndex(4L),
            com.google.common.collect.ImmutableSet.of(SrSidBinding.Flag.PROTECTED));
    owner.setSegmentRoutingConfig(
        new SegmentRoutingConfig(
            com.google.common.collect.ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
            SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 23999L))),
            null,
            ImmutableMap.of(
                DEFAULT_VRF_NAME,
                new SegmentRoutingVrfConfig(
                    DEFAULT_VRF_NAME, ImmutableList.of(binding, adjacency)))));
  }

  private static void addLink(
      NetworkFactory nf,
      Map<String, Configuration> configurations,
      String left,
      String leftInterface,
      String leftAddress,
      long leftCost,
      String right,
      String rightInterface,
      String rightAddress,
      long rightCost) {
    addInterface(nf, configurations.get(left), leftInterface, leftAddress, leftCost, false);
    addInterface(nf, configurations.get(right), rightInterface, rightAddress, rightCost, false);
  }

  private static void addInterface(
      NetworkFactory nf,
      Configuration owner,
      String name,
      String address,
      long cost,
      boolean passive) {
    IsisInterfaceLevelSettings level =
        IsisInterfaceLevelSettings.builder()
            .setCost(cost)
            .setMode(passive ? IsisInterfaceMode.PASSIVE : IsisInterfaceMode.ACTIVE)
            .build();
    IsisInterfaceSettings settings =
        IsisInterfaceSettings.builder().setPointToPoint(true).setLevel1(level).build();
    nf.interfaceBuilder()
        .setOwner(owner)
        .setVrf(owner.getDefaultVrf())
        .setName(name)
        .setAddress(ConcreteInterfaceAddress.parse(address))
        .setIsis(settings)
        .build();
  }
}
