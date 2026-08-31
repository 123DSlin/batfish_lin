package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Stable node/VRF/color/endpoint identity of one SR policy. */
@ParametersAreNonnullByDefault
public final class SrPolicyKey implements Serializable {
  private static final String PROP_NODE = "node";
  private static final String PROP_VRF = "vrf";
  private static final String PROP_COLOR = "color";
  private static final String PROP_ENDPOINT = "endpoint";

  private final String _node;
  private final String _vrf;
  private final long _color;
  private final SrPolicyEndpoint _endpoint;

  @JsonCreator
  public SrPolicyKey(
      @Nullable @JsonProperty(PROP_NODE) String node,
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @JsonProperty(PROP_COLOR) long color,
      @Nullable @JsonProperty(PROP_ENDPOINT) SrPolicyEndpoint endpoint) {
    checkArgument(node != null && !node.isEmpty(), "SR policy node must be provided");
    checkArgument(vrf != null && !vrf.isEmpty(), "SR policy VRF must be provided");
    checkArgument(
        color >= 0L && color <= SrCandidatePath.MAX_UNSIGNED_INT,
        "SR policy color must be an unsigned integer");
    checkArgument(endpoint != null, "SR policy endpoint must be provided");
    _node = node;
    _vrf = vrf;
    _color = color;
    _endpoint = endpoint;
  }

  @JsonProperty(PROP_NODE)
  public String getNode() {
    return _node;
  }

  @JsonProperty(PROP_VRF)
  public String getVrf() {
    return _vrf;
  }

  @JsonProperty(PROP_COLOR)
  public long getColor() {
    return _color;
  }

  @JsonProperty(PROP_ENDPOINT)
  public SrPolicyEndpoint getEndpoint() {
    return _endpoint;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrPolicyKey)) {
      return false;
    }
    SrPolicyKey that = (SrPolicyKey) object;
    return _color == that._color
        && _node.equals(that._node)
        && _vrf.equals(that._vrf)
        && _endpoint.equals(that._endpoint);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_node, _vrf, _color, _endpoint);
  }
}
