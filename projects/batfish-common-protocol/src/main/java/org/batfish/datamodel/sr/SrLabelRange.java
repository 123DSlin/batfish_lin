package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** One inclusive MPLS label range in an SRGB or SRLB. */
@ParametersAreNonnullByDefault
public final class SrLabelRange implements Serializable {
  private static final String PROP_START = "start";
  private static final String PROP_END = "end";

  private final long _start;
  private final long _end;

  @JsonCreator
  private static SrLabelRange create(
      @Nullable @JsonProperty(PROP_START) Long start, @Nullable @JsonProperty(PROP_END) Long end) {
    checkArgument(start != null, "Missing %s", PROP_START);
    checkArgument(end != null, "Missing %s", PROP_END);
    return new SrLabelRange(start, end);
  }

  public static SrLabelRange of(long start, long end) {
    return new SrLabelRange(start, end);
  }

  private SrLabelRange(long start, long end) {
    checkArgument(start >= 0, "MPLS label range start must be nonnegative");
    checkArgument(end >= start, "MPLS label range end must not precede start");
    checkArgument(end <= SrSidValue.MAX_MPLS_LABEL, "MPLS label range exceeds 20-bit range");
    _start = start;
    _end = end;
  }

  @JsonProperty(PROP_START)
  public long getStart() {
    return _start;
  }

  @JsonProperty(PROP_END)
  public long getEnd() {
    return _end;
  }

  public long size() {
    return _end - _start + 1L;
  }

  public boolean contains(long label) {
    return label >= _start && label <= _end;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrLabelRange)) {
      return false;
    }
    SrLabelRange that = (SrLabelRange) object;
    return _start == that._start && _end == that._end;
  }

  @Override
  public int hashCode() {
    return Objects.hash(_start, _end);
  }
}
