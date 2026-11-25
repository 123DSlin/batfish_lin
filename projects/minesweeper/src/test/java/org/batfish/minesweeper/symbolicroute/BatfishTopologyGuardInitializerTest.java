package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import com.google.common.collect.ImmutableMap;
import com.microsoft.z3.Context;
import java.util.Map;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.InterfaceType;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Vrf;
import org.junit.Test;

/** Physical failure guards must not be inferred from shared anycast loopback prefixes. */
public final class BatfishTopologyGuardInitializerTest {

  @Test
  public void testSharedLoopbackPrefixDoesNotCreateLinkOrDisableLocalSeeds() {
    NetworkFactory nf = new NetworkFactory();
    Configuration c = configuration(nf, "c");
    Configuration i = configuration(nf, "i");
    Map<String, Configuration> configurations = ImmutableMap.of("c", c, "i", i);
    try (Context context = new Context()) {
      Z3RouteGuardFactory guards = new Z3RouteGuardFactory(context);
      TopologyLinkGuards topology =
          BatfishTopologyGuardInitializer.inferTopology(configurations, guards);

      assertTrue(topology.getGuardsByKey().isEmpty());
      assertNull(topology.getKey("c", "Loopback0"));
      assertNull(topology.getKey("i", "Loopback0"));
      for (Configuration configuration : configurations.values()) {
        assertEquals(
            1, BatfishInterfaceRouteInitializer.build(configuration, topology, guards).size());
        assertTrue(
            BatfishInterfaceRouteInitializer.build(configuration, topology, guards).stream()
                .allMatch(seed -> seed.getGuard().isEquivalentTo(guards.trueGuard())));
        assertTrue(
            BatfishInterfaceRouteInitializer.build(configuration, topology, guards).stream()
                .allMatch(seed -> seed.getLinkFailureKey() == null));
      }
    }
  }

  @Test
  public void testPhysicalLinkRemainsWithSharedLoopbackPrefix() {
    NetworkFactory nf = new NetworkFactory();
    Configuration c = configuration(nf, "c");
    Configuration i = configuration(nf, "i");
    addInterface(nf, c, "Ethernet0", "10.0.0.1/30", InterfaceType.PHYSICAL);
    addInterface(nf, i, "Ethernet0", "10.0.0.2/30", InterfaceType.PHYSICAL);
    try (Context context = new Context()) {
      TopologyLinkGuards topology =
          BatfishTopologyGuardInitializer.inferTopology(
              ImmutableMap.of("c", c, "i", i), new Z3RouteGuardFactory(context));

      assertEquals(1, topology.getGuardsByKey().size());
      assertEquals(LinkFailureKey.of("c", "i"), topology.getKey("c", "Ethernet0"));
      assertEquals(LinkFailureKey.of("c", "i"), topology.getKey("i", "Ethernet0"));
      assertNull(topology.getKey("c", "Loopback0"));
      assertNull(topology.getKey("i", "Loopback0"));
    }
  }

  private static Configuration configuration(NetworkFactory nf, String hostname) {
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname(hostname)
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    nf.vrfBuilder().setOwner(configuration).setName(DEFAULT_VRF_NAME).build();
    addInterface(nf, configuration, "Loopback0", "5.5.5.5/32", InterfaceType.LOOPBACK);
    return configuration;
  }

  private static void addInterface(
      NetworkFactory nf,
      Configuration configuration,
      String name,
      String address,
      InterfaceType type) {
    Vrf vrf = configuration.getVrfs().get(DEFAULT_VRF_NAME);
    nf.interfaceBuilder()
        .setOwner(configuration)
        .setVrf(vrf)
        .setName(name)
        .setAddress(ConcreteInterfaceAddress.parse(address))
        .setType(type)
        .build();
  }
}
