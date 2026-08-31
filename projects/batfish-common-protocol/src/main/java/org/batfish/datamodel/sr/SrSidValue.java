package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;
import org.batfish.datamodel.Ip6;

/**
 * Vendor-independent, typed Segment Routing SID value.
 *
 * <p>{@link Type#MPLS_LABEL} is a resolved 20-bit label that may appear on the wire. {@link
 * Type#MPLS_INDEX} is an unresolved, nonnegative allocation index; it is not a label. Prefix/Node
 * SID forwarding resolves it against the relevant next hop's SRGB, while local SID types use their
 * explicitly selected local block. This value object deliberately selects neither namespace nor
 * block.
 */
@ParametersAreNonnullByDefault
public final class SrSidValue implements Serializable {
  public enum Type {
    MPLS_LABEL,
    MPLS_INDEX,
    SRV6
  }

  private static final String PROP_TYPE = "type";
  private static final String PROP_NUMERIC_VALUE = "numericValue";
  private static final String PROP_SRV6_VALUE = "srv6Value";
  public static final long MAX_MPLS_LABEL = 1_048_575L;

  private final Type _type;
  @Nullable private final Long _numericValue;
  @Nullable private final Ip6 _srv6Value;

  @JsonCreator
  private static SrSidValue create(
      @Nullable @JsonProperty(PROP_TYPE) Type type,
      @Nullable @JsonProperty(PROP_NUMERIC_VALUE) Long numericValue,
      @Nullable @JsonProperty(PROP_SRV6_VALUE) Ip6 srv6Value) {
    checkArgument(type != null, "Missing %s", PROP_TYPE);
    return new SrSidValue(type, numericValue, srv6Value);
  }

  public static SrSidValue mplsLabel(long label) {
    return new SrSidValue(Type.MPLS_LABEL, label, null);
  }

  public static SrSidValue mplsIndex(long index) {
    return new SrSidValue(Type.MPLS_INDEX, index, null);
  }

  public static SrSidValue srv6(Ip6 sid) {
    return new SrSidValue(Type.SRV6, null, sid);
  }

  private SrSidValue(Type type, @Nullable Long numericValue, @Nullable Ip6 srv6Value) {
    _type = type;
    if (type == Type.SRV6) {
      checkArgument(numericValue == null, "SRv6 SID cannot have a numeric MPLS value");
      checkArgument(srv6Value != null, "SRv6 SID value must be provided");
    } else {
      checkArgument(srv6Value == null, "MPLS SID cannot have an SRv6 value");
      checkArgument(numericValue != null && numericValue >= 0, "MPLS value must be nonnegative");
      if (type == Type.MPLS_LABEL) {
        checkArgument(numericValue <= MAX_MPLS_LABEL, "MPLS label exceeds 20-bit range");
      }
    }
    _numericValue = numericValue;
    _srv6Value = srv6Value;
  }

  @JsonProperty(PROP_TYPE)
  public Type getType() {
    return _type;
  }

  @Nullable
  @JsonProperty(PROP_NUMERIC_VALUE)
  /** JSON representation shared by the two tagged MPLS variants; prefer the typed accessors. */
  public Long getNumericValue() {
    return _numericValue;
  }

  @Nullable
  @JsonProperty(PROP_SRV6_VALUE)
  public Ip6 getSrv6Value() {
    return _srv6Value;
  }

  /** Returns the resolved wire label and rejects unresolved indexes and SRv6 SIDs. */
  @JsonIgnore
  public long getMplsLabel() {
    checkArgument(_type == Type.MPLS_LABEL, "SID value is not a resolved MPLS label");
    return _numericValue;
  }

  /** Returns the unresolved SRGB-relative index and rejects labels and SRv6 SIDs. */
  @JsonIgnore
  public long getMplsIndex() {
    checkArgument(_type == Type.MPLS_INDEX, "SID value is not an MPLS index");
    return _numericValue;
  }

  /** Returns the SRv6 SID and rejects both MPLS variants. */
  @JsonIgnore
  public Ip6 getSrv6Sid() {
    checkArgument(_type == Type.SRV6, "SID value is not an SRv6 SID");
    return _srv6Value;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof SrSidValue)) return false;
    SrSidValue that = (SrSidValue) o;
    return _type == that._type
        && Objects.equals(_numericValue, that._numericValue)
        && Objects.equals(_srv6Value, that._srv6Value);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_type, _numericValue, _srv6Value);
  }
}
