package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.BgpSessionProperties.SessionType.EBGP_SINGLEHOP;
import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.batfish.datamodel.ConfigurationFormat.CISCO_IOS;
import static org.batfish.datamodel.RoutingProtocol.BGP;
import static org.batfish.datamodel.bgp.AddressFamily.Type.IPV4_UNICAST;
import static org.batfish.datamodel.routing_policy.statement.Statements.ExitAccept;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.util.Map;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpActivePeerConfig;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.BgpSessionProperties;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.GenericRibReadOnly;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.Vrf;
import org.batfish.datamodel.bgp.Ipv4UnicastAddressFamily;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.datamodel.routing_policy.RoutingPolicy;
import org.batfish.dataplane.rib.Rib;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Whole-pipeline tests from guarded main-RIB seeds to every router's final symbolic RIB. */
@RunWith(JUnit4.class)
public final class BatfishSymbolicRoutePipelineTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Test
  public void testRejectsUnmatchedBgpSessionBeforeRunning() {
    NetworkFactory nf = new NetworkFactory();
    Configuration first =
        nf.configurationBuilder().setHostname("r1").setConfigurationFormat(CISCO_IOS).build();
    Configuration second =
        nf.configurationBuilder().setHostname("r2").setConfigurationFormat(CISCO_IOS).build();
    RouteGuard link = GUARDS.variable("unmatched");
    BatfishSymbolicRoutePipelineInput input =
        new BatfishSymbolicRoutePipelineInput(
            ImmutableMap.of("r1", first, "r2", second),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(new SymbolicRouteSession("missing", "r1", "r2", link)),
            ImmutableMap.of(
                "r1",
                ImmutableMap.of(DEFAULT_VRF_NAME, new Rib()),
                "r2",
                ImmutableMap.of(DEFAULT_VRF_NAME, new Rib())));

    boolean rejected = false;
    try {
      BatfishSymbolicRoutePipeline.run(input);
    } catch (IllegalArgumentException e) {
      rejected = true;
    }
    assertThat(rejected, equalTo(true));
  }

  @Test
  public void testRejectsMissingRedistributionPolicyInsteadOfDroppingRoute() {
    NetworkFactory nf = new NetworkFactory();
    Configuration router =
        nf.configurationBuilder().setHostname("r").setConfigurationFormat(CISCO_IOS).build();
    Vrf vrf = nf.vrfBuilder().setOwner(router).setName(DEFAULT_VRF_NAME).build();
    vrf.setBgpProcess(process("1.1.1.1"));
    AnnotatedRoute<AbstractRoute> connected =
        new AnnotatedRoute<>(
            new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Loopback0"), DEFAULT_VRF_NAME);
    Rib mainRib = new Rib();
    mainRib.mergeRoute(connected);
    BatfishSymbolicRoutePipelineInput input =
        new BatfishSymbolicRoutePipelineInput(
            ImmutableMap.of("r", router),
            ImmutableList.of(
                new SymbolicRouteSeed<>("connected", "r", connected, GUARDS.trueGuard())),
            ImmutableList.of(),
            ImmutableList.of(
                new BatfishBgpRedistributionRule(
                    "missing-policy-rule",
                    "r",
                    DEFAULT_VRF_NAME,
                    DEFAULT_VRF_NAME,
                    "DOES_NOT_EXIST",
                    BGP)),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableMap.of("r", ImmutableMap.of(DEFAULT_VRF_NAME, mainRib)));

    boolean rejected = false;
    try {
      BatfishSymbolicRoutePipeline.run(input);
    } catch (IllegalArgumentException e) {
      rejected = true;
    }
    assertThat(rejected, equalTo(true));
  }

  @Test
  public void testRejectsMissingRouterMainRibContext() {
    NetworkFactory nf = new NetworkFactory();
    Configuration first =
        nf.configurationBuilder().setHostname("r1").setConfigurationFormat(CISCO_IOS).build();
    Configuration second =
        nf.configurationBuilder().setHostname("r2").setConfigurationFormat(CISCO_IOS).build();
    BatfishSymbolicRoutePipelineInput input =
        new BatfishSymbolicRoutePipelineInput(
            ImmutableMap.of("r1", first, "r2", second),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableList.of(),
            ImmutableMap.of("r1", ImmutableMap.of(DEFAULT_VRF_NAME, new Rib())));

    boolean rejected = false;
    try {
      BatfishSymbolicRoutePipeline.run(input);
    } catch (IllegalArgumentException e) {
      rejected = true;
    }
    assertThat(rejected, equalTo(true));
  }

  @Test
  public void testConnectedRecursiveStaticAndEbgpConvergeInOneRun() {
    NetworkFactory nf = new NetworkFactory();
    Configuration a =
        nf.configurationBuilder().setHostname("a").setConfigurationFormat(CISCO_IOS).build();
    Configuration b =
        nf.configurationBuilder().setHostname("b").setConfigurationFormat(CISCO_IOS).build();
    Configuration c =
        nf.configurationBuilder().setHostname("c").setConfigurationFormat(CISCO_IOS).build();
    RoutingPolicy.builder()
        .setOwner(a)
        .setName("redistribute")
        .addStatement(ExitAccept.toStaticStatement())
        .build();
    RoutingPolicy.builder()
        .setOwner(a)
        .setName("export")
        .addStatement(ExitAccept.toStaticStatement())
        .build();
    RoutingPolicy.builder()
        .setOwner(b)
        .setName("import")
        .addStatement(ExitAccept.toStaticStatement())
        .build();
    BgpProcess aProcess = process("1.1.1.1");
    BgpProcess bProcess = process("2.2.2.2");
    Vrf aVrf = nf.vrfBuilder().setOwner(a).setName(DEFAULT_VRF_NAME).build();
    Vrf bVrf = nf.vrfBuilder().setOwner(b).setName(DEFAULT_VRF_NAME).build();
    nf.vrfBuilder().setOwner(c).setName(DEFAULT_VRF_NAME).build();
    aVrf.setBgpProcess(aProcess);
    bVrf.setBgpProcess(bProcess);
    BgpActivePeerConfig aPeer =
        BgpActivePeerConfig.builder()
            .setLocalAs(65001L)
            .setLocalIp(Ip.parse("10.0.0.1"))
            .setPeerAddress(Ip.parse("10.0.0.2"))
            .setRemoteAs(65002L)
            .setIpv4UnicastAddressFamily(
                Ipv4UnicastAddressFamily.builder().setExportPolicy("export").build())
            .build();
    BgpActivePeerConfig bPeer =
        BgpActivePeerConfig.builder()
            .setLocalAs(65002L)
            .setLocalIp(Ip.parse("10.0.0.2"))
            .setPeerAddress(Ip.parse("10.0.0.1"))
            .setRemoteAs(65001L)
            .setIpv4UnicastAddressFamily(
                Ipv4UnicastAddressFamily.builder().setImportPolicy("import").build())
            .build();
    BatfishBgpEdge edge =
        new BatfishBgpEdge(
            "a-b",
            DEFAULT_VRF_NAME,
            DEFAULT_VRF_NAME,
            a,
            b,
            aPeer,
            bPeer,
            aProcess,
            bProcess,
            session(65002L, 65001L, "10.0.0.2", "10.0.0.1"),
            session(65001L, 65002L, "10.0.0.1", "10.0.0.2"),
            Ip.parse("10.0.0.1"),
            null,
            false);
    RouteGuard connectedGuard = GUARDS.variable("connected_enabled");
    RouteGuard staticGuard = GUARDS.variable("static_enabled");
    RouteGuard linkGuard = GUARDS.variable("a_b_session");
    AnnotatedRoute<AbstractRoute> connected =
        new AnnotatedRoute<>(
            new ConnectedRoute(Prefix.parse("10.10.0.0/24"), "Ethernet0"), DEFAULT_VRF_NAME);
    StaticRoute recursive =
        StaticRoute.testBuilder()
            .setNetwork(Prefix.parse("192.0.2.0/24"))
            .setNextHop(NextHopIp.of(Ip.parse("10.10.0.1")))
            .build();
    Rib aMainRib = new Rib();
    aMainRib.mergeRoute(connected);
    aMainRib.mergeRoute(new AnnotatedRoute<>(recursive, DEFAULT_VRF_NAME));
    Rib bMainRib = new Rib();

    BatfishSymbolicRoutePipelineResult result =
        BatfishSymbolicRoutePipeline.run(
            new BatfishSymbolicRoutePipelineInput(
                ImmutableMap.of("a", a, "b", b, "c", c),
                ImmutableList.of(
                    new SymbolicRouteSeed<>("a-connected", "a", connected, connectedGuard)),
                ImmutableList.of(
                    new SymbolicStaticRoute(
                        "a-static",
                        "a",
                        new AnnotatedRoute<>(recursive, DEFAULT_VRF_NAME),
                        staticGuard)),
                ImmutableList.of(
                    new BatfishBgpRedistributionRule(
                        "a-redist", "a", DEFAULT_VRF_NAME, DEFAULT_VRF_NAME, "redistribute", BGP)),
                ImmutableList.of(edge),
                ImmutableList.of(new SymbolicRouteSession("a-b", "a", "b", linkGuard)),
                mainRibs(aMainRib, bMainRib, new Rib())));

    assertThat(result.getMainRibNetwork().getRib("a").getEntries(), hasSize(2));
    assertThat(result.getBgpRibNetwork().getRib("a").getEntries(), hasSize(2));
    assertThat(result.getBgpRibNetwork().getRib("b").getEntries(), hasSize(2));
    assertThat(result.getAllRoutes(), hasSize(8));
    assertThat(
        result.getMainRibNetwork().getRib("b").getEntries().stream()
            .filter(entry -> entry.getSymbolicRoute().getKey().getProtocol() == BGP)
            .count(),
        equalTo(2L));
    GuardedRibEntry<AnnotatedRoute<org.batfish.datamodel.Bgpv4Route>> receivedStatic =
        result.getBgpRibNetwork().getRib("b").getEntries().stream()
            .filter(
                entry ->
                    entry.getSymbolicRoute().getKey().getNetwork().equals(recursive.getNetwork()))
            .findFirst()
            .get();
    assertThat(
        receivedStatic
            .getAvailabilityGuard()
            .isEquivalentTo(connectedGuard.and(staticGuard).and(linkGuard)),
        equalTo(true));
    SymbolicRibRecord record =
        result.getAllRoutes().stream()
            .filter(
                candidate ->
                    candidate.getPlane() == SymbolicRibRecord.Plane.BGP
                        && candidate.getRouter().equals("b")
                        && candidate.getPrefix().equals("192.0.2.0/24"))
            .findFirst()
            .get();
    assertThat(record.getVrf(), equalTo(DEFAULT_VRF_NAME));
    assertThat(record.getRouterPath(), equalTo(ImmutableList.of("a", "b")));
    assertThat(result.getRoutesByRouterAndVrf().get("b").get(DEFAULT_VRF_NAME), hasSize(4));
    assertThat(result.getRoutesByRouterAndVrf().get("c").get(DEFAULT_VRF_NAME), hasSize(0));
    assertThat(result.getRoutes("c", DEFAULT_VRF_NAME), hasSize(0));
    boolean unknownRouterRejected = false;
    try {
      result.getRoutes("missing", DEFAULT_VRF_NAME);
    } catch (IllegalArgumentException e) {
      unknownRouterRejected = true;
    }
    assertThat(unknownRouterRejected, equalTo(true));
    assertThat(result.toJson(), containsString("\"availabilityGuard\""));
    assertThat(result.toJson(), containsString("connected_enabled"));

    SymbolicRouteContributionId connectedContribution =
        new SymbolicRouteContributionId("a-connected", "a", "a");
    result.getMainRibNetwork().getEngine().withdraw(ImmutableList.of(connectedContribution));
    assertThat(hasPrefix(result.getBgpRibNetwork(), "a", connected.getNetwork()), equalTo(false));
    assertThat(hasPrefix(result.getBgpRibNetwork(), "b", connected.getNetwork()), equalTo(false));
    assertThat(hasPrefix(result.getMainRibNetwork(), "b", connected.getNetwork()), equalTo(false));

    RouteGuard updatedConnectedGuard = GUARDS.variable("connected_updated");
    result
        .getMainRibNetwork()
        .getEngine()
        .converge(
            ImmutableList.of(
                new SymbolicRouteSeed<>("a-connected", "a", connected, updatedConnectedGuard)
                    .toMessage()));
    assertThat(hasPrefix(result.getBgpRibNetwork(), "a", connected.getNetwork()), equalTo(true));
    assertThat(
        bgpPrefixAt(result, "b", connected.getNetwork())
            .getAvailabilityGuard()
            .isEquivalentTo(updatedConnectedGuard.and(linkGuard)),
        equalTo(true));
    assertThat(
        mainPrefixAt(result, "b", connected.getNetwork())
            .getAvailabilityGuard()
            .isEquivalentTo(updatedConnectedGuard.and(linkGuard)),
        equalTo(true));
  }

  private static <R extends org.batfish.datamodel.AbstractRouteDecorator> boolean hasPrefix(
      SymbolicRouteNetwork<R> network, String router, Prefix prefix) {
    return network.getRib(router).getEntries().stream()
        .anyMatch(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(prefix));
  }

  private static GuardedRibEntry<AnnotatedRoute<org.batfish.datamodel.Bgpv4Route>> bgpPrefixAt(
      BatfishSymbolicRoutePipelineResult result, String router, Prefix prefix) {
    return result.getBgpRibNetwork().getRib(router).getEntries().stream()
        .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(prefix))
        .findFirst()
        .get();
  }

  private static GuardedRibEntry<AnnotatedRoute<AbstractRoute>> mainPrefixAt(
      BatfishSymbolicRoutePipelineResult result, String router, Prefix prefix) {
    return result.getMainRibNetwork().getRib(router).getEntries().stream()
        .filter(entry -> entry.getSymbolicRoute().getKey().getNetwork().equals(prefix))
        .findFirst()
        .get();
  }

  private static BgpProcess process(String routerId) {
    return BgpProcess.builder()
        .setAdminCostsToVendorDefaults(CISCO_IOS)
        .setRouterId(Ip.parse(routerId))
        .build();
  }

  private static BgpSessionProperties session(
      long tailAs, long headAs, String tailIp, String headIp) {
    return BgpSessionProperties.builder()
        .setAddressFamilies(ImmutableList.of(IPV4_UNICAST))
        .setTailAs(tailAs)
        .setHeadAs(headAs)
        .setTailIp(Ip.parse(tailIp))
        .setHeadIp(Ip.parse(headIp))
        .setSessionType(EBGP_SINGLEHOP)
        .build();
  }

  private static Map<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
      mainRibs(Rib aMainRib, Rib bMainRib, Rib cMainRib) {
    return ImmutableMap.of(
        "a", ImmutableMap.of(DEFAULT_VRF_NAME, aMainRib),
        "b", ImmutableMap.of(DEFAULT_VRF_NAME, bMainRib),
        "c", ImmutableMap.of(DEFAULT_VRF_NAME, cMainRib));
  }
}
