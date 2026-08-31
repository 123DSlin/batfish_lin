package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** One stable SR policy candidate referencing a locally configured segment list. */
@ParametersAreNonnullByDefault
public final class SrCandidatePath implements Serializable {
  private static final String PROP_NAME = "name";
  private static final String PROP_PREFERENCE = "preference";
  private static final String PROP_WEIGHT = "weight";
  private static final String PROP_SEGMENT_LIST = "segmentList";
  public static final long MAX_UNSIGNED_INT = 0xFFFFFFFFL;

  private final String _name;
  private final long _preference;
  private final long _weight;
  private final String _segmentList;

  @JsonCreator
  public SrCandidatePath(
      @Nullable @JsonProperty(PROP_NAME) String name,
      @JsonProperty(PROP_PREFERENCE) long preference,
      @JsonProperty(PROP_WEIGHT) long weight,
      @Nullable @JsonProperty(PROP_SEGMENT_LIST) String segmentList) {
    checkArgument(name != null && !name.isEmpty(), "Candidate-path name must be provided");
    checkArgument(
        preference >= 0L && preference <= MAX_UNSIGNED_INT,
        "Candidate preference must be an unsigned integer");
    checkArgument(
        weight > 0L && weight <= MAX_UNSIGNED_INT,
        "Candidate weight must be a positive unsigned integer");
    checkArgument(
        segmentList != null && !segmentList.isEmpty(),
        "Candidate segment-list reference must be provided");
    _name = name;
    _preference = preference;
    _weight = weight;
    _segmentList = segmentList;
  }

  @JsonProperty(PROP_NAME)
  public String getName() {
    return _name;
  }

  @JsonProperty(PROP_PREFERENCE)
  public long getPreference() {
    return _preference;
  }

  @JsonProperty(PROP_WEIGHT)
  public long getWeight() {
    return _weight;
  }

  @JsonProperty(PROP_SEGMENT_LIST)
  public String getSegmentList() {
    return _segmentList;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrCandidatePath)) {
      return false;
    }
    SrCandidatePath that = (SrCandidatePath) object;
    return _preference == that._preference
        && _weight == that._weight
        && _name.equals(that._name)
        && _segmentList.equals(that._segmentList);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_name, _preference, _weight, _segmentList);
  }
}
