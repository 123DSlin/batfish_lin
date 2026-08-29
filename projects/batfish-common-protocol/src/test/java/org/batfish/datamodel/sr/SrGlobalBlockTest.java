package org.batfish.datamodel.sr;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Ip6;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests for ordered SR global-block index resolution. */
@RunWith(JUnit4.class)
public final class SrGlobalBlockTest {

  @Test
  public void testOrderedMultiRangeResolution() {
    SrGlobalBlock block =
        SrGlobalBlock.of(
            ImmutableList.of(SrLabelRange.of(16000L, 16002L), SrLabelRange.of(20000L, 20001L)));

    assertThat(block.size(), equalTo(5L));
    assertThat(block.resolve(SrSidValue.mplsIndex(0L)), equalTo(SrSidValue.mplsLabel(16000L)));
    assertThat(block.resolve(SrSidValue.mplsIndex(2L)), equalTo(SrSidValue.mplsLabel(16002L)));
    assertThat(block.resolve(SrSidValue.mplsIndex(3L)), equalTo(SrSidValue.mplsLabel(20000L)));
    assertThat(block.resolve(SrSidValue.mplsIndex(4L)), equalTo(SrSidValue.mplsLabel(20001L)));
  }

  @Test
  public void testOrderIsSemantic() {
    SrGlobalBlock first =
        SrGlobalBlock.of(
            ImmutableList.of(SrLabelRange.of(100L, 101L), SrLabelRange.of(200L, 201L)));
    SrGlobalBlock second =
        SrGlobalBlock.of(
            ImmutableList.of(SrLabelRange.of(200L, 201L), SrLabelRange.of(100L, 101L)));

    assertThat(first.resolve(SrSidValue.mplsIndex(0L)), equalTo(SrSidValue.mplsLabel(100L)));
    assertThat(second.resolve(SrSidValue.mplsIndex(0L)), equalTo(SrSidValue.mplsLabel(200L)));
  }

  @Test
  public void testRejectsInvalidRangesAndResolution() {
    assertThrows(IllegalArgumentException.class, () -> SrLabelRange.of(-1L, 1L));
    assertThrows(IllegalArgumentException.class, () -> SrLabelRange.of(2L, 1L));
    assertThrows(
        IllegalArgumentException.class, () -> SrLabelRange.of(0L, SrSidValue.MAX_MPLS_LABEL + 1L));
    assertThrows(IllegalArgumentException.class, () -> SrGlobalBlock.of(ImmutableList.of()));
    assertThrows(
        IllegalArgumentException.class,
        () -> SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(0L, 100L))));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            SrGlobalBlock.of(
                ImmutableList.of(SrLabelRange.of(100L, 200L), SrLabelRange.of(150L, 250L))));
    SrGlobalBlock block = SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 16009L)));
    assertThrows(IllegalArgumentException.class, () -> block.resolve(SrSidValue.mplsIndex(10L)));
    assertThrows(IllegalArgumentException.class, () -> block.resolve(SrSidValue.mplsLabel(0L)));
    assertThrows(
        IllegalArgumentException.class,
        () -> block.resolve(SrSidValue.srv6(Ip6.parse("2001:db8::1"))));
  }

  @Test
  public void testJsonRoundTrip() {
    SrGlobalBlock block =
        SrGlobalBlock.of(
            ImmutableList.of(SrLabelRange.of(16000L, 16009L), SrLabelRange.of(20000L, 20009L)));
    assertThat(BatfishObjectMapper.clone(block, SrGlobalBlock.class), equalTo(block));
  }

  private interface ThrowingRunnable {
    void run() throws Exception;
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
