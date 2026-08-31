package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableList;
import java.io.Serializable;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Immutable normalized segment list ordered by explicit configuration sequence. */
@ParametersAreNonnullByDefault
public final class SrSegmentList implements Serializable {
  private static final String PROP_KEY = "key";
  private static final String PROP_SEGMENTS = "segments";

  private final SrSegmentListKey _key;
  private final ImmutableList<SrSegment> _segments;

  @JsonCreator
  public SrSegmentList(
      @Nullable @JsonProperty(PROP_KEY) SrSegmentListKey key,
      @Nullable @JsonProperty(PROP_SEGMENTS) List<SrSegment> segments) {
    checkArgument(key != null, "Segment-list key must be provided");
    checkArgument(segments != null && !segments.isEmpty(), "Segment list must not be empty");
    Set<Long> orders = new HashSet<>();
    for (SrSegment segment : segments) {
      checkArgument(orders.add(segment.getOrder()), "Duplicate segment order");
      SrSidBindingKey bindingKey = segment.getBindingKey();
      checkArgument(
          bindingKey == null || bindingKey.getVrf().equals(key.getVrf()),
          "Referenced SID binding must use the segment-list VRF");
    }
    _key = key;
    _segments =
        segments.stream()
            .sorted(Comparator.comparingLong(SrSegment::getOrder))
            .collect(ImmutableList.toImmutableList());
  }

  @JsonProperty(PROP_KEY)
  public SrSegmentListKey getKey() {
    return _key;
  }

  @JsonProperty(PROP_SEGMENTS)
  public ImmutableList<SrSegment> getSegments() {
    return _segments;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrSegmentList)) {
      return false;
    }
    SrSegmentList that = (SrSegmentList) object;
    return _key.equals(that._key) && _segments.equals(that._segments);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_key, _segments);
  }
}
