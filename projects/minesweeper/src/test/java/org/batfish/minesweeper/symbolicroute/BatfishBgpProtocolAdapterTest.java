package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.BgpSessionProperties.SessionType.EBGP_SINGLEHOP;
import static org.batfish.datamodel.ConfigurationFormat.CISCO_IOS;
import static org.batfish.datamodel.RoutingProtocol.BGP;
import static org.batfish.datamodel.RoutingProtocol.CONNECTED;
import static org.batfish.datamodel.bgp.AddressFamily.Type.IPV4_UNICAST;
import static org.batfish.datamodel.routing_policy.statement.Statements.ExitAccept;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpActivePeerConfig;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.BgpSessionProperties;
import org.batfish.datamodel.BgpTieBreaker;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.bgp.Ipv4UnicastAddressFamily;
import org.batfish.datamodel.routing_policy.RoutingPolicy;
import org.batfish.dataplane.rib.Bgpv4Rib;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** End-to-end tests for connected/static redistribution and Batfish-backed eBGP propagation. */
@RunWith(JUnit4.class)
public final class BatfishBgpProtocolAdapterTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Test
  public void testBgpPreferenceDelegatesToBatfishBgpRib() {
    Bgpv4Route high =
        Bgpv4Route.testBuilder()
            .setNetwork(Prefix.parse("203.0.113.0/24"))
            .setLocalPreference(200L)
            .build();
    Bgpv4Route low = high.toBuilder().setLocalPreference(100L).build();
    BatfishBgpProtocolAdapter adapter = new BatfishBgpProtocolAdapter(ImmutableList.of());
    Bgpv4Rib oracle = new Bgpv4Rib(null, BgpTieBreaker.ROUTER_ID, 1, null, false, false);

    assertThat(
        Integer.signum(
            adapter
                .preferenceComparator("r")
                .compare(
                    new AnnotatedRoute<>(high, "default"), new AnnotatedRoute<>(low, "default"))),
        equalTo(-Integer.signum(oracle.comparePreference(high, low))));
  }

  @Test
  public void testConnectedRouteUsesBatfishNonBgpConversion() {
    NetworkFactory nf = new NetworkFactory();
    Configuration configuration =
        nf.configurationBuilder().setHostname("r").setConfigurationFormat(CISCO_IOS).build();
    RoutingPolicy.builder()
        .setOwner(configuration)
        .setName("redistribute-connected")
        .addStatement(ExitAccept.toStaticStatement())
        .build();
    BgpProcess process =
        BgpProcess.builder()
            .setAdminCostsToVendorDefaults(CISCO_IOS)
            .setRouterId(Ip.parse("1.1.1.1"))
            .build();
    AnnotatedRoute<AbstractRoute> connected =
        new AnnotatedRoute<>(
            new ConnectedRoute(Prefix.parse("198.51.100.0/24"), "Ethernet0"), "blue");

    BatfishRoutingPolicyResult<Bgpv4Route> result =
        BatfishBgpRedistribution.redistribute(
            configuration,
            process,
            "redistribute-connected",
            connected,
            "blue",
            Ip.parse("1.1.1.1"),
            BGP);

    assertThat(result.getOutcome(), equalTo(BatfishRoutingPolicyResult.Outcome.ACCEPTED));
    assertThat(result.getOutputRoute().get().getRoute().getSrcProtocol(), equalTo(CONNECTED));
    assertThat(result.getOutputRoute().get().getSourceVrf(), equalTo("blue"));
  }

  @Test
  public void testStaticRedistributionAndEbgpPropagationPreserveSymbolicGuard() {
    NetworkFactory nf = new NetworkFactory();
    Configuration a =
        nf.configurationBuilder().setHostname("a").setConfigurationFormat(CISCO_IOS).build();
    Configuration b =
        nf.configurationBuilder().setHostname("b").setConfigurationFormat(CISCO_IOS).build();
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
    BgpProcess aProcess =
        BgpProcess.builder()
            .setAdminCostsToVendorDefaults(CISCO_IOS)
            .setRouterId(Ip.parse("1.1.1.1"))
            .build();
    BgpProcess bProcess =
        BgpProcess.builder()
            .setAdminCostsToVendorDefaults(CISCO_IOS)
            .setRouterId(Ip.parse("2.2.2.2"))
            .build();
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
    BgpSessionProperties exportProperties = session(65002L, 65001L, "10.0.0.2", "10.0.0.1");
    BgpSessionProperties importProperties = session(65001L, 65002L, "10.0.0.1", "10.0.0.2");
    BatfishBgpEdge edge =
        new BatfishBgpEdge(
            "a-b",
            "default",
            "default",
            a,
            b,
            aPeer,
            bPeer,
            aProcess,
            bProcess,
            exportProperties,
            importProperties,
            Ip.parse("10.0.0.1"),
            null,
            false);
    AnnotatedRoute<AbstractRoute> statik =
        new AnnotatedRoute<>(
            StaticRoute.testBuilder().setNetwork(Prefix.parse("192.0.2.0/24")).build(), "default");
    BatfishRoutingPolicyResult<Bgpv4Route> originated =
        BatfishBgpRedistribution.redistribute(
            a, aProcess, "redistribute", statik, "default", Ip.parse("10.0.0.1"), BGP);
    RouteGuard sourceGuard = GUARDS.variable("source_guard");
    RouteGuard linkGuard = GUARDS.variable("bgp_link");
    AnnotatedRoute<Bgpv4Route> seedRoute = originated.getOutputRoute().get();
    SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of("a", "b"),
            ImmutableList.of(new SymbolicRouteSession("a-b", "a", "b", linkGuard)),
            ImmutableList.of(new SymbolicRouteSeed<>("origin", "a", seedRoute, sourceGuard)),
            new BatfishBgpProtocolAdapter(ImmutableList.of(edge)));

    network.converge();

    assertThat(network.getRib("b").getEntries(), hasSize(1));
    GuardedRibEntry<AnnotatedRoute<Bgpv4Route>> received = network.getRib("b").getEntries().get(0);
    assertThat(
        received.getAvailabilityGuard().isEquivalentTo(sourceGuard.and(linkGuard)), equalTo(true));
    assertThat(received.getSymbolicRoute().getRoute().getSourceVrf(), equalTo("default"));
    assertThat(received.getSymbolicRoute().getRoute().getRoute().getProtocol(), equalTo(BGP));
    assertThat(
        received.getSymbolicRoute().getRoute().getRoute().getAsPath().containsAs(65001L),
        equalTo(true));
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
}
