package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableList;
import java.io.Serializable;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** One configured SR policy and its stable candidate-path contributions. */
@ParametersAreNonnullByDefault
public final class SrPolicy implements Serializable {
  private static final String PROP_KEY = "key";
  private static final String PROP_NAME = "name";
  private static final String PROP_CANDIDATES = "candidates";

  private final SrPolicyKey _key;
  private final String _name;
  private final ImmutableList<SrCandidatePath> _candidates;

  @JsonCreator
  public SrPolicy(
      @Nullable @JsonProperty(PROP_KEY) SrPolicyKey key,
      @Nullable @JsonProperty(PROP_NAME) String name,
      @Nullable @JsonProperty(PROP_CANDIDATES) List<SrCandidatePath> candidates) {
    checkArgument(key != null, "SR policy key must be provided");
    checkArgument(name != null && !name.isEmpty(), "SR policy name must be provided");
    checkArgument(candidates != null && !candidates.isEmpty(), "SR policy needs a candidate path");
    Set<String> identities = new HashSet<>();
    for (SrCandidatePath candidate : candidates) {
      checkArgument(identities.add(candidate.getName()), "Duplicate candidate-path identity");
    }
    _key = key;
    _name = name;
    _candidates = ImmutableList.copyOf(candidates);
  }

  @JsonProperty(PROP_KEY)
  public SrPolicyKey getKey() {
    return _key;
  }

  @JsonProperty(PROP_NAME)
  public String getName() {
    return _name;
  }

  @JsonProperty(PROP_CANDIDATES)
  public ImmutableList<SrCandidatePath> getCandidates() {
    return _candidates;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrPolicy)) {
      return false;
    }
    SrPolicy that = (SrPolicy) object;
    return _key.equals(that._key)
        && _name.equals(that._name)
        && _candidates.equals(that._candidates);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_key, _name, _candidates);
  }
}
