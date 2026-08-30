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

/** Vendor-independent Segment Routing configuration scoped to one VRF. */
@ParametersAreNonnullByDefault
public final class SegmentRoutingVrfConfig implements Serializable {
  private static final String PROP_VRF = "vrf";
  private static final String PROP_SID_BINDINGS = "sidBindings";

  private final String _vrf;
  private final ImmutableList<SrSidBinding> _sidBindings;

  @JsonCreator
  public SegmentRoutingVrfConfig(
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @Nullable @JsonProperty(PROP_SID_BINDINGS) List<SrSidBinding> sidBindings) {
    checkArgument(vrf != null && !vrf.isEmpty(), "SR VRF must be provided");
    _vrf = vrf;
    _sidBindings = sidBindings == null ? ImmutableList.of() : ImmutableList.copyOf(sidBindings);
    Set<SrSidBindingKey> identities = new HashSet<>();
    for (SrSidBinding binding : _sidBindings) {
      checkArgument(binding.getKey().getVrf().equals(vrf), "SID binding VRF does not match owner");
      checkArgument(identities.add(binding.getKey()), "Duplicate SID binding identity");
    }
  }

  @JsonProperty(PROP_VRF)
  public String getVrf() {
    return _vrf;
  }

  @JsonProperty(PROP_SID_BINDINGS)
  public ImmutableList<SrSidBinding> getSidBindings() {
    return _sidBindings;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SegmentRoutingVrfConfig)) {
      return false;
    }
    SegmentRoutingVrfConfig that = (SegmentRoutingVrfConfig) object;
    return _vrf.equals(that._vrf) && _sidBindings.equals(that._sidBindings);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_vrf, _sidBindings);
  }
}
