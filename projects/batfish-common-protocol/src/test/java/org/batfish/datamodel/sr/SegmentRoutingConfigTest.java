package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.Prefix;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests device/VRF isolation and serialization of vendor-independent SR configuration. */
@RunWith(JUnit4.class)
public final class SegmentRoutingConfigTest {

  @Test
  public void testConfigurationJsonRoundTripPreservesSrConfig() {
    SegmentRoutingConfig srConfig = config("blue", binding("r1", "blue", 7L));
    Configuration configuration = new Configuration("r1", ConfigurationFormat.CISCO_IOS);
    configuration.setSegmentRoutingConfig(srConfig);

    Configuration cloned = BatfishObjectMapper.clone(configuration, Configuration.class);

    assertThat(cloned.getSegmentRoutingConfig(), equalTo(srConfig));
  }

  @Test
  public void testVrfIsolation() {
    SrSidBinding blue = binding("r1", "blue", 7L);
    SrSidBinding red = binding("r1", "red", 8L);
    SegmentRoutingConfig config =
        new SegmentRoutingConfig(
            ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
            srgb(),
            srlb(),
            ImmutableMap.of(
                "blue", new SegmentRoutingVrfConfig("blue", ImmutableList.of(blue)),
                "red", new SegmentRoutingVrfConfig("red", ImmutableList.of(red))));

    assertThat(config.getVrfs().get("blue").getSidBindings(), equalTo(ImmutableList.of(blue)));
    assertThat(config.getVrfs().get("red").getSidBindings(), equalTo(ImmutableList.of(red)));
  }

  @Test
  public void testRejectsInvalidOwnershipAndDuplicateIdentity() {
    SrSidBinding binding = binding("r1", "blue", 7L);
    assertThrows(() -> new SegmentRoutingVrfConfig("red", ImmutableList.of(binding)));
    assertThrows(() -> new SegmentRoutingVrfConfig("blue", ImmutableList.of(binding, binding)));
    assertThrows(() -> config("blue", binding("r2", "blue", 7L)).validateOwner("r1"));
  }

  @Test
  public void testRejectsInvalidDeviceStructure() {
    SegmentRoutingVrfConfig blue =
        new SegmentRoutingVrfConfig("blue", ImmutableList.of(binding("r1", "blue", 7L)));
    assertThrows(() -> new SegmentRoutingConfig(ImmutableSet.of(), null, null, ImmutableMap.of()));
    assertThrows(
        () ->
            new SegmentRoutingConfig(
                ImmutableSet.of(SegmentRoutingConfig.DataPlane.SRV6),
                srgb(),
                null,
                ImmutableMap.of()));
    assertThrows(
        () ->
            new SegmentRoutingConfig(
                ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
                srgb(),
                srlb(),
                ImmutableMap.of("red", blue)));
  }

  @Test
  public void testSrlbIsAllocationPoolNotIndexResolver() {
    SrLocalBlock block = srlb();
    assertThat(block.contains(15000L), equalTo(true));
    assertThat(block.contains(15999L), equalTo(true));
    assertThat(block.contains(16000L), equalTo(false));
    assertThat(BatfishObjectMapper.clone(block, SrLocalBlock.class), equalTo(block));
  }

  private static SegmentRoutingConfig config(String vrf, SrSidBinding binding) {
    return new SegmentRoutingConfig(
        ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
        srgb(),
        srlb(),
        ImmutableMap.of(vrf, new SegmentRoutingVrfConfig(vrf, ImmutableList.of(binding))));
  }

  private static SrSidBinding binding(String node, String vrf, long index) {
    return new SrSidBinding(
        new SrSidBindingKey(
            node,
            vrf,
            SrSidBindingKey.Type.PREFIX,
            0,
            SrPrefix.ipv4(Prefix.parse("10.0.0.0/24")),
            null,
            null),
        SrSidValue.mplsIndex(index),
        ImmutableSet.of());
  }

  private static SrGlobalBlock srgb() {
    return SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 23999L)));
  }

  private static SrLocalBlock srlb() {
    return SrLocalBlock.of(ImmutableList.of(SrLabelRange.of(15000L, 15999L)));
  }

  private interface ThrowingRunnable {
    void run() throws Exception;
  }

  private static void assertThrows(ThrowingRunnable operation) {
    try {
      operation.run();
      throw new AssertionError("Expected IllegalArgumentException");
    } catch (IllegalArgumentException expected) {
      // Expected.
    } catch (Exception unexpected) {
      throw new AssertionError(unexpected);
    }
  }
}
