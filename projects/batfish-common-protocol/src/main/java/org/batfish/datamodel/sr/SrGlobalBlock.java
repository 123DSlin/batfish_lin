package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableList;
import java.io.Serializable;
import java.util.List;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Ordered, non-overlapping label ranges that form one Segment Routing global block. */
@ParametersAreNonnullByDefault
public final class SrGlobalBlock implements Serializable {
  private static final String PROP_RANGES = "ranges";
  public static final long MIN_ALLOCATABLE_LABEL = 16L;

  private final ImmutableList<SrLabelRange> _ranges;
  private final long _size;

  @JsonCreator
  private static SrGlobalBlock create(
      @Nullable @JsonProperty(PROP_RANGES) List<SrLabelRange> ranges) {
    checkArgument(ranges != null, "Missing %s", PROP_RANGES);
    return new SrGlobalBlock(ranges);
  }

  public static SrGlobalBlock of(Iterable<SrLabelRange> ranges) {
    return new SrGlobalBlock(ImmutableList.copyOf(ranges));
  }

  private SrGlobalBlock(Iterable<SrLabelRange> ranges) {
    _ranges = ImmutableList.copyOf(ranges);
    checkArgument(!_ranges.isEmpty(), "SR global block must contain at least one range");
    long size = 0L;
    for (int index = 0; index < _ranges.size(); index++) {
      SrLabelRange range = _ranges.get(index);
      checkArgument(
          range.getStart() >= MIN_ALLOCATABLE_LABEL,
          "SR global block cannot allocate reserved MPLS labels");
      for (int previous = 0; previous < index; previous++) {
        SrLabelRange old = _ranges.get(previous);
        checkArgument(
            range.getEnd() < old.getStart() || range.getStart() > old.getEnd(),
            "SR global block ranges must not overlap");
      }
      size = Math.addExact(size, range.size());
    }
    _size = size;
  }

  @JsonProperty(PROP_RANGES)
  public ImmutableList<SrLabelRange> getRanges() {
    return _ranges;
  }

  public long size() {
    return _size;
  }

  /** Resolves an SRGB-relative index to a new absolute MPLS label value. */
  public SrSidValue resolve(SrSidValue unresolved) {
    checkArgument(unresolved.getType() == SrSidValue.Type.MPLS_INDEX, "SID must be an MPLS index");
    long remaining = unresolved.getMplsIndex();
    checkArgument(remaining < _size, "MPLS index is outside the SR global block");
    for (SrLabelRange range : _ranges) {
      if (remaining < range.size()) {
        return SrSidValue.mplsLabel(Math.addExact(range.getStart(), remaining));
      }
      remaining -= range.size();
    }
    throw new IllegalStateException("validated SRGB index did not resolve");
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    return object instanceof SrGlobalBlock && _ranges.equals(((SrGlobalBlock) object)._ranges);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_ranges);
  }
}
