package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableSet;
import com.google.common.testing.EqualsTester;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.Prefix6;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests stable SID binding identity, validation, and serialization. */
@RunWith(JUnit4.class)
public final class SrSidBindingTest {
  @Test
  public void testIpv4AndIpv6RoundTrip() {
    SrSidBinding ipv4 = binding(key("r1", "blue", SrPrefix.ipv4(Prefix.parse("10.0.0.0/24")), 0));
    SrSidBinding ipv6 =
        binding(key("r1", "blue", SrPrefix.ipv6(Prefix6.parse("2001:db8::/64")), 128));
    assertThat(BatfishObjectMapper.clone(ipv4, SrSidBinding.class), equalTo(ipv4));
    assertThat(BatfishObjectMapper.clone(ipv6, SrSidBinding.class), equalTo(ipv6));
  }

  @Test
  public void testIdentitySeparatesNodeVrfAlgorithmAndType() {
    SrPrefix prefix = SrPrefix.ipv4(Prefix.parse("10.0.0.0/24"));
    new EqualsTester()
        .addEqualityGroup(key("r1", "blue", prefix, 0), key("r1", "blue", prefix, 0))
        .addEqualityGroup(key("r2", "blue", prefix, 0))
        .addEqualityGroup(key("r1", "red", prefix, 0))
        .addEqualityGroup(key("r1", "blue", prefix, 1))
        .addEqualityGroup(
            new SrSidBindingKey("r1", "blue", SrSidBindingKey.Type.NODE, 0, prefix, null, null))
        .testEquals();
  }

  @Test
  public void testTypeSpecificFieldsAreExclusive() {
    SrPrefix prefix = SrPrefix.ipv4(Prefix.parse("10.0.0.0/24"));
    assertThrows(
        () -> new SrSidBindingKey("r1", "blue", SrSidBindingKey.Type.PREFIX, 0, null, null, null));
    assertThrows(
        () ->
            new SrSidBindingKey(
                "r1", "blue", SrSidBindingKey.Type.ADJACENCY, 0, prefix, "Eth0", null));
    assertThrows(
        () ->
            new SrSidBindingKey(
                "r1", "blue", SrSidBindingKey.Type.ADJACENCY, 1, null, "Eth0", null));
    assertThrows(
        () -> new SrSidBindingKey("r1", "blue", SrSidBindingKey.Type.BINDING, 0, null, null, ""));
  }

  private static SrSidBinding binding(SrSidBindingKey key) {
    return new SrSidBinding(
        key, SrSidValue.mplsIndex(7L), ImmutableSet.of(SrSidBinding.Flag.NO_PHP));
  }

  private static SrSidBindingKey key(String node, String vrf, SrPrefix prefix, int algorithm) {
    return new SrSidBindingKey(
        node, vrf, SrSidBindingKey.Type.PREFIX, algorithm, prefix, null, null);
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
