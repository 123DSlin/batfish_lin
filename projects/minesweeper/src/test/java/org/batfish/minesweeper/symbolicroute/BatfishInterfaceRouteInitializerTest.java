package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.util.List;
import java.util.stream.Collectors;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.ConnectedRouteMetadata;
import org.batfish.datamodel.NetworkFactory;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests exact Batfish connected/local initialization semantics under symbolic guards. */
@RunWith(JUnit4.class)
public final class BatfishInterfaceRouteInitializerTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Test
  public void testDefaultGenerationAndInactiveInterface() {
    NetworkFactory nf = new NetworkFactory();
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname("r1")
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setName("active")
        .setAddress(ConcreteInterfaceAddress.parse("1.1.1.1/24"))
        .build();
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setName("host")
        .setAddress(ConcreteInterfaceAddress.parse("2.2.2.2/32"))
        .build();
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setName("inactive")
        .setActive(false)
        .setAddress(ConcreteInterfaceAddress.parse("3.3.3.3/24"))
        .build();

    List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> seeds = build(configuration);

    assertThat(seeds, hasSize(3));
    assertThat(
        seeds.stream().map(SymbolicRouteSeed::getMessageId).collect(Collectors.toList()),
        containsInAnyOrder(
            "connected:r1:active:1.1.1.1/24",
            "local:r1:active:1.1.1.1/24",
            "connected:r1:host:2.2.2.2/32"));
  }

  @Test
  public void testMetadataControlsGenerationAndRouteAttributes() {
    NetworkFactory nf = new NetworkFactory();
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname("r1")
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    ConcreteInterfaceAddress localOnly = ConcreteInterfaceAddress.parse("1.1.1.1/32");
    ConcreteInterfaceAddress connectedOnly = ConcreteInterfaceAddress.parse("2.2.2.2/24");
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setName("local-only")
        .setAddress(localOnly)
        .setAddressMetadata(
            ImmutableMap.of(
                localOnly,
                ConnectedRouteMetadata.builder()
                    .setGenerateConnectedRoute(false)
                    .setGenerateLocalRoute(true)
                    .setAdmin(17)
                    .setTag(23)
                    .build()))
        .build();
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setName("connected-only")
        .setAddress(connectedOnly)
        .setAddressMetadata(
            ImmutableMap.of(
                connectedOnly,
                ConnectedRouteMetadata.builder().setGenerateLocalRoute(false).build()))
        .build();

    List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> seeds = build(configuration);

    assertThat(seeds, hasSize(2));
    SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>> local =
        seeds.stream().filter(seed -> seed.getMessageId().startsWith("local:")).findFirst().get();
    AbstractRoute localRoute = local.toMessage().getRoute().getRoute();
    assertThat(localRoute.getAdministrativeCost(), equalTo(17));
    assertThat(localRoute.getTag(), equalTo(23L));
    assertThat(
        seeds.stream().map(SymbolicRouteSeed::getMessageId).collect(Collectors.toList()),
        containsInAnyOrder(
            "local:r1:local-only:1.1.1.1/32", "connected:r1:connected-only:2.2.2.2/24"));
  }

  private static List<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> build(
      Configuration configuration) {
    return BatfishInterfaceRouteInitializer.build(
        configuration, new TopologyLinkGuards(ImmutableMap.of(), ImmutableMap.of()), GUARDS);
  }
}
