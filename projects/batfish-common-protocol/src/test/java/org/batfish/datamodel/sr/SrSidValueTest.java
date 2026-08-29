package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.google.common.testing.EqualsTester;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Ip6;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests for {@link SrSidValue}. */
@RunWith(JUnit4.class)
public final class SrSidValueTest {

  private interface ThrowingRunnable {
    void run() throws Exception;
  }

  private static final ObjectMapper MAPPER = BatfishObjectMapper.mapper();

  @Test
  public void testTypedAccessorsDoNotConfuseIndexAndLabel() {
    SrSidValue label = SrSidValue.mplsLabel(16000L);
    SrSidValue index = SrSidValue.mplsIndex(7L);

    assertThat(label.getMplsLabel(), equalTo(16000L));
    assertThat(index.getMplsIndex(), equalTo(7L));
    assertThrows(IllegalArgumentException.class, label::getMplsIndex);
    assertThrows(IllegalArgumentException.class, index::getMplsLabel);
  }

  @Test
  public void testMplsLabelBounds() {
    assertThat(SrSidValue.mplsLabel(0L).getMplsLabel(), equalTo(0L));
    assertThat(
        SrSidValue.mplsLabel(SrSidValue.MAX_MPLS_LABEL).getMplsLabel(),
        equalTo(SrSidValue.MAX_MPLS_LABEL));
    assertThrows(IllegalArgumentException.class, () -> SrSidValue.mplsLabel(-1L));
    assertThrows(
        IllegalArgumentException.class, () -> SrSidValue.mplsLabel(SrSidValue.MAX_MPLS_LABEL + 1L));
    assertThrows(IllegalArgumentException.class, () -> SrSidValue.mplsIndex(-1L));
  }

  @Test
  public void testSrv6Value() {
    Ip6 sid = Ip6.parse("2001:db8::1");
    SrSidValue value = SrSidValue.srv6(sid);

    assertThat(value.getSrv6Sid(), equalTo(sid));
    assertThrows(IllegalArgumentException.class, value::getMplsLabel);
    assertThrows(IllegalArgumentException.class, value::getMplsIndex);
  }

  @Test
  public void testJsonRoundTrip() {
    for (SrSidValue value :
        new SrSidValue[] {
          SrSidValue.mplsLabel(16000L),
          SrSidValue.mplsIndex(42L),
          SrSidValue.srv6(Ip6.parse("2001:db8::1"))
        }) {
      assertThat(BatfishObjectMapper.clone(value, SrSidValue.class), equalTo(value));
    }
  }

  @Test
  public void testJsonRejectsInvalidTaggedUnions() throws Exception {
    assertJsonRejected("{\"numericValue\":1}");
    assertJsonRejected("{\"type\":\"SRV6\",\"numericValue\":1}");
    assertJsonRejected("{\"type\":\"SRV6\"}");
    assertJsonRejected("{\"type\":\"MPLS_LABEL\",\"srv6Value\":\"2001:db8::1\"}");
    assertJsonRejected("{\"type\":\"MPLS_LABEL\",\"numericValue\":1048576}");
    assertJsonRejected("{\"type\":\"MPLS_INDEX\",\"numericValue\":-1}");
  }

  @Test
  public void testEquals() {
    new EqualsTester()
        .addEqualityGroup(SrSidValue.mplsLabel(16L), SrSidValue.mplsLabel(16L))
        .addEqualityGroup(SrSidValue.mplsLabel(17L))
        .addEqualityGroup(SrSidValue.mplsIndex(16L))
        .addEqualityGroup(SrSidValue.srv6(Ip6.parse("2001:db8::1")))
        .testEquals();
  }

  private static void assertJsonRejected(String json) throws Exception {
    JsonNode node = MAPPER.readTree(json);
    assertThrows(Exception.class, () -> MAPPER.treeToValue(node, SrSidValue.class));
  }

  private static void assertThrows(
      Class<? extends Throwable> expected, ThrowingRunnable operation) {
    try {
      operation.run();
      throw new AssertionError("Expected " + expected.getSimpleName());
    } catch (Throwable thrown) {
      if (!expected.isInstance(thrown)) {
        throw new AssertionError(
            "Expected " + expected.getSimpleName() + " but caught " + thrown, thrown);
      }
    }
  }
}
