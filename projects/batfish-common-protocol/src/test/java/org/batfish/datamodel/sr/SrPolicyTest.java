package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Ip6;
import org.batfish.datamodel.Prefix;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests stable policy identity, ordered segments, references, and JSON persistence. */
@RunWith(JUnit4.class)
public final class SrPolicyTest {

  @Test
  public void testPolicyModelRoundTripAndOrdering() {
    SrSegmentList segmentList = segmentList("r1", "blue", "to-r2");
    SrPolicy policy = policy("r1", "blue", "gold", 100L, "to-r2");
    SegmentRoutingVrfConfig vrf =
        new SegmentRoutingVrfConfig(
            "blue", ImmutableList.of(), ImmutableList.of(segmentList), ImmutableList.of(policy));
    SegmentRoutingConfig sr =
        new SegmentRoutingConfig(
            ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
            SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 23999L))),
            null,
            ImmutableMap.of("blue", vrf));
    Configuration configuration = new Configuration("r1", ConfigurationFormat.CISCO_IOS);
    configuration.setSegmentRoutingConfig(sr);

    Configuration clone = BatfishObjectMapper.clone(configuration, Configuration.class);

    assertThat(clone.getSegmentRoutingConfig(), equalTo(sr));
    assertThat(vrf.getSegmentLists(), hasSize(1));
    assertThat(vrf.getPolicies(), hasSize(1));
    assertThat(segmentList.getSegments().get(0).getOrder(), equalTo(10L));
    assertThat(segmentList.getSegments().get(1).getOrder(), equalTo(20L));
  }

  @Test
  public void testIpv4AndIpv6PolicyIdentityRemainDistinct() {
    SrPolicyKey ipv4 =
        new SrPolicyKey("r1", "blue", 100L, SrPolicyEndpoint.ipv4(Ip.parse("192.0.2.1")));
    SrPolicyKey ipv6 =
        new SrPolicyKey("r1", "blue", 100L, SrPolicyEndpoint.ipv6(Ip6.parse("2001:db8::1")));
    assertThat(BatfishObjectMapper.clone(ipv4, SrPolicyKey.class), equalTo(ipv4));
    assertThat(BatfishObjectMapper.clone(ipv6, SrPolicyKey.class), equalTo(ipv6));
    assertThat(ipv4.equals(ipv6), equalTo(false));
  }

  @Test
  public void testRejectsInvalidSegmentUnionAndOrder() {
    SrSidBindingKey bindingKey = bindingKey("r2", "blue");
    assertThrows(() -> new SrSegment(10L, null, null));
    assertThrows(() -> new SrSegment(10L, bindingKey, SrSidValue.mplsLabel(16001L)));
    assertThrows(() -> new SrSegment(10L, null, SrSidValue.mplsIndex(7L)));
    assertThrows(() -> new SrSegment(-1L, bindingKey, null));
    assertThrows(() -> new SrSegment(SrSegment.MAX_ORDER + 1L, bindingKey, null));
    assertThrows(
        () ->
            new SrSegmentList(
                new SrSegmentListKey("r1", "blue", "duplicate"),
                ImmutableList.of(
                    new SrSegment(10L, bindingKey, null),
                    new SrSegment(10L, null, SrSidValue.mplsLabel(16001L)))));
    assertThrows(
        () ->
            new SrSegmentList(
                new SrSegmentListKey("r1", "blue", "cross-vrf"),
                ImmutableList.of(new SrSegment(10L, bindingKey("r2", "red"), null))));
  }

  @Test
  public void testRejectsInvalidCandidatesAndReferences() {
    assertThrows(() -> new SrCandidatePath("c", 1L, 0L, "list"));
    assertThrows(() -> new SrCandidatePath("c", SrCandidatePath.MAX_UNSIGNED_INT + 1L, 1L, "list"));
    SrCandidatePath candidate = new SrCandidatePath("c", 200L, 1L, "missing");
    SrPolicyKey key =
        new SrPolicyKey("r1", "blue", 100L, SrPolicyEndpoint.ipv4(Ip.parse("192.0.2.1")));
    assertThrows(
        () -> new SrPolicy(key, "duplicate-candidate", ImmutableList.of(candidate, candidate)));
    assertThrows(
        () ->
            new SegmentRoutingVrfConfig(
                "blue",
                ImmutableList.of(),
                ImmutableList.of(segmentList("r1", "blue", "defined")),
                ImmutableList.of(
                    new SrPolicy(key, "undefined-reference", ImmutableList.of(candidate)))));
  }

  @Test
  public void testRejectsDuplicatePolicyAndWrongOwner() {
    SrSegmentList list = segmentList("r1", "blue", "to-r2");
    SrPolicy first = policy("r1", "blue", "first", 100L, "to-r2");
    SrPolicy sameIdentity = policy("r1", "blue", "second", 100L, "to-r2");
    assertThrows(
        () ->
            new SegmentRoutingVrfConfig(
                "blue",
                ImmutableList.of(),
                ImmutableList.of(list),
                ImmutableList.of(first, sameIdentity)));
    SegmentRoutingConfig config =
        new SegmentRoutingConfig(
            ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
            null,
            null,
            ImmutableMap.of(
                "blue",
                new SegmentRoutingVrfConfig(
                    "blue", ImmutableList.of(), ImmutableList.of(list), ImmutableList.of(first))));
    assertThrows(() -> config.validateOwner("r9"));
  }

  private static SrSegmentList segmentList(String node, String vrf, String name) {
    return new SrSegmentList(
        new SrSegmentListKey(node, vrf, name),
        ImmutableList.of(
            new SrSegment(20L, null, SrSidValue.mplsLabel(15004L)),
            new SrSegment(10L, bindingKey("r2", vrf), null)));
  }

  private static SrPolicy policy(
      String node, String vrf, String name, long color, String segmentList) {
    return new SrPolicy(
        new SrPolicyKey(node, vrf, color, SrPolicyEndpoint.ipv4(Ip.parse("192.0.2.1"))),
        name,
        ImmutableList.of(new SrCandidatePath("candidate-1", 200L, 1L, segmentList)));
  }

  private static SrSidBindingKey bindingKey(String node, String vrf) {
    return new SrSidBindingKey(
        node,
        vrf,
        SrSidBindingKey.Type.PREFIX,
        0,
        SrPrefix.ipv4(Prefix.parse("10.0.0.0/24")),
        null,
        null);
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
