package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** One ordered segment expressed as either a typed binding reference or an explicit SID value. */
@ParametersAreNonnullByDefault
public final class SrSegment implements Serializable {
  private static final String PROP_ORDER = "order";
  private static final String PROP_BINDING_KEY = "bindingKey";
  private static final String PROP_SID = "sid";
  public static final long MAX_ORDER = 0xFFFFFFFFL;

  private final long _order;
  @Nullable private final SrSidBindingKey _bindingKey;
  @Nullable private final SrSidValue _sid;

  @JsonCreator
  public SrSegment(
      @JsonProperty(PROP_ORDER) long order,
      @Nullable @JsonProperty(PROP_BINDING_KEY) SrSidBindingKey bindingKey,
      @Nullable @JsonProperty(PROP_SID) SrSidValue sid) {
    checkArgument(order >= 0L && order <= MAX_ORDER, "Segment order must be an unsigned integer");
    checkArgument(
        (bindingKey == null) != (sid == null),
        "Segment must contain exactly one binding reference or explicit SID");
    checkArgument(
        sid == null || sid.getType() != SrSidValue.Type.MPLS_INDEX,
        "An explicit segment cannot carry an unscoped MPLS index");
    _order = order;
    _bindingKey = bindingKey;
    _sid = sid;
  }

  @JsonProperty(PROP_ORDER)
  public long getOrder() {
    return _order;
  }

  @Nullable
  @JsonProperty(PROP_BINDING_KEY)
  public SrSidBindingKey getBindingKey() {
    return _bindingKey;
  }

  @Nullable
  @JsonProperty(PROP_SID)
  public SrSidValue getSid() {
    return _sid;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrSegment)) {
      return false;
    }
    SrSegment that = (SrSegment) object;
    return _order == that._order
        && Objects.equals(_bindingKey, that._bindingKey)
        && Objects.equals(_sid, that._sid);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_order, _bindingKey, _sid);
  }
}
