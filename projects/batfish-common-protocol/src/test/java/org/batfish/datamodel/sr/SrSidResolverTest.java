package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import org.batfish.datamodel.Ip6;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests explicit MPLS SID resolution boundaries. */
@RunWith(JUnit4.class)
public final class SrSidResolverTest {
  private static final SrGlobalBlock SRGB =
      SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(45000L, 55000L)));

  @Test
  public void testAbsoluteLabelIsAlreadyResolved() {
    SrSidValue label = SrSidValue.mplsLabel(16001L);
    assertThat(SrSidResolver.resolveMpls(label, null), equalTo(label));
  }

  @Test
  public void testIndexUsesDeviceSrgb() {
    assertThat(
        SrSidResolver.resolveMpls(SrSidValue.mplsIndex(2L), SRGB),
        equalTo(SrSidValue.mplsLabel(45002L)));
  }

  @Test
  public void testRejectsMissingBlockOutOfRangeAndSrv6() {
    assertThrows(() -> SrSidResolver.resolveMpls(SrSidValue.mplsIndex(2L), null));
    assertThrows(() -> SrSidResolver.resolveMpls(SrSidValue.mplsIndex(10001L), SRGB));
    assertThrows(() -> SrSidResolver.resolveMpls(SrSidValue.srv6(Ip6.parse("2001:db8::1")), SRGB));
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
