package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Stable device/VRF/name identity of one configured SR segment list. */
@ParametersAreNonnullByDefault
public final class SrSegmentListKey implements Serializable {
  private static final String PROP_NODE = "node";
  private static final String PROP_VRF = "vrf";
  private static final String PROP_NAME = "name";

  private final String _node;
  private final String _vrf;
  private final String _name;

  @JsonCreator
  public SrSegmentListKey(
      @Nullable @JsonProperty(PROP_NODE) String node,
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @Nullable @JsonProperty(PROP_NAME) String name) {
    checkArgument(node != null && !node.isEmpty(), "Segment-list node must be provided");
    checkArgument(vrf != null && !vrf.isEmpty(), "Segment-list VRF must be provided");
    checkArgument(name != null && !name.isEmpty(), "Segment-list name must be provided");
    _node = node;
    _vrf = vrf;
    _name = name;
  }

  @JsonProperty(PROP_NODE)
  public String getNode() {
    return _node;
  }

  @JsonProperty(PROP_VRF)
  public String getVrf() {
    return _vrf;
  }

  @JsonProperty(PROP_NAME)
  public String getName() {
    return _name;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrSegmentListKey)) {
      return false;
    }
    SrSegmentListKey that = (SrSegmentListKey) object;
    return _node.equals(that._node) && _vrf.equals(that._vrf) && _name.equals(that._name);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_node, _vrf, _name);
  }
}
