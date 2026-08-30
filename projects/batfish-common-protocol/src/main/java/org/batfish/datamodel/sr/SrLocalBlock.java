package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableList;
import java.io.Serializable;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Local label ranges from which a node may allocate adjacency or binding SIDs. */
@ParametersAreNonnullByDefault
public final class SrLocalBlock implements Serializable {
  private static final String PROP_RANGES = "ranges";

  private final ImmutableList<SrLabelRange> _ranges;

  @JsonCreator
  public static SrLocalBlock of(@Nullable @JsonProperty(PROP_RANGES) List<SrLabelRange> ranges) {
    checkArgument(ranges != null && !ranges.isEmpty(), "SRLB must contain at least one range");
    ImmutableList<SrLabelRange> copied = ImmutableList.copyOf(ranges);
    copied.forEach(
        range ->
            checkArgument(
                range.getStart() >= SrGlobalBlock.MIN_ALLOCATABLE_LABEL,
                "SRLB must not contain reserved MPLS labels"));
    ImmutableList<SrLabelRange> sorted =
        copied.stream()
            .sorted(Comparator.comparingLong(SrLabelRange::getStart))
            .collect(ImmutableList.toImmutableList());
    for (int index = 1; index < sorted.size(); index++) {
      checkArgument(
          sorted.get(index - 1).getEnd() < sorted.get(index).getStart(),
          "SRLB ranges must not overlap");
    }
    return new SrLocalBlock(copied);
  }

  private SrLocalBlock(ImmutableList<SrLabelRange> ranges) {
    _ranges = ranges;
  }

  @JsonProperty(PROP_RANGES)
  public ImmutableList<SrLabelRange> getRanges() {
    return _ranges;
  }

  public boolean contains(long label) {
    return _ranges.stream().anyMatch(range -> range.getStart() <= label && label <= range.getEnd());
  }

  @Override
  public boolean equals(Object object) {
    return this == object
        || object instanceof SrLocalBlock && _ranges.equals(((SrLocalBlock) object)._ranges);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_ranges);
  }
}
