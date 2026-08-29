package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableSet;
import java.io.Serializable;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Configured SID value and behavior flags associated with a stable binding identity. */
@ParametersAreNonnullByDefault
public final class SrSidBinding implements Serializable {
  public enum Flag {
    EXPLICIT_NULL,
    NO_PHP,
    PERSISTENT,
    LOCAL
  }

  private static final String PROP_KEY = "key";
  private static final String PROP_SID = "sid";
  private static final String PROP_FLAGS = "flags";
  private final SrSidBindingKey _key;
  private final SrSidValue _sid;
  private final ImmutableSet<Flag> _flags;

  @JsonCreator
  public SrSidBinding(
      @Nullable @JsonProperty(PROP_KEY) SrSidBindingKey key,
      @Nullable @JsonProperty(PROP_SID) SrSidValue sid,
      @Nullable @JsonProperty(PROP_FLAGS) Set<Flag> flags) {
    checkArgument(key != null, "SID binding key must be provided");
    checkArgument(sid != null, "SID value must be provided");
    _key = key;
    _sid = sid;
    _flags = flags == null ? ImmutableSet.of() : ImmutableSet.copyOf(flags);
  }

  @JsonProperty(PROP_KEY)
  public SrSidBindingKey getKey() {
    return _key;
  }

  @JsonProperty(PROP_SID)
  public SrSidValue getSid() {
    return _sid;
  }

  @JsonProperty(PROP_FLAGS)
  public ImmutableSet<Flag> getFlags() {
    return _flags;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof SrSidBinding)) return false;
    SrSidBinding that = (SrSidBinding) o;
    return _key.equals(that._key) && _sid.equals(that._sid) && _flags.equals(that._flags);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_key, _sid, _flags);
  }
}
