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
  private static final String PROP_SEGMENT_LISTS = "segmentLists";
  private static final String PROP_POLICIES = "policies";

  private final String _vrf;
  private final ImmutableList<SrSidBinding> _sidBindings;
  private final ImmutableList<SrSegmentList> _segmentLists;
  private final ImmutableList<SrPolicy> _policies;

  public SegmentRoutingVrfConfig(
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @Nullable @JsonProperty(PROP_SID_BINDINGS) List<SrSidBinding> sidBindings) {
    this(vrf, sidBindings, null, null);
  }

  @JsonCreator
  public SegmentRoutingVrfConfig(
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @Nullable @JsonProperty(PROP_SID_BINDINGS) List<SrSidBinding> sidBindings,
      @Nullable @JsonProperty(PROP_SEGMENT_LISTS) List<SrSegmentList> segmentLists,
      @Nullable @JsonProperty(PROP_POLICIES) List<SrPolicy> policies) {
    checkArgument(vrf != null && !vrf.isEmpty(), "SR VRF must be provided");
    _vrf = vrf;
    _sidBindings = sidBindings == null ? ImmutableList.of() : ImmutableList.copyOf(sidBindings);
    _segmentLists = segmentLists == null ? ImmutableList.of() : ImmutableList.copyOf(segmentLists);
    _policies = policies == null ? ImmutableList.of() : ImmutableList.copyOf(policies);
    Set<SrSidBindingKey> identities = new HashSet<>();
    for (SrSidBinding binding : _sidBindings) {
      checkArgument(binding.getKey().getVrf().equals(vrf), "SID binding VRF does not match owner");
      checkArgument(identities.add(binding.getKey()), "Duplicate SID binding identity");
    }
    Set<String> segmentListNames = new HashSet<>();
    for (SrSegmentList segmentList : _segmentLists) {
      checkArgument(segmentList.getKey().getVrf().equals(vrf), "Segment-list VRF mismatch");
      checkArgument(
          segmentListNames.add(segmentList.getKey().getName()), "Duplicate segment-list identity");
    }
    Set<SrPolicyKey> policyIdentities = new HashSet<>();
    Set<String> policyNames = new HashSet<>();
    for (SrPolicy policy : _policies) {
      checkArgument(policy.getKey().getVrf().equals(vrf), "SR policy VRF mismatch");
      checkArgument(policyIdentities.add(policy.getKey()), "Duplicate SR policy identity");
      checkArgument(policyNames.add(policy.getName()), "Duplicate SR policy name");
      for (SrCandidatePath candidate : policy.getCandidates()) {
        checkArgument(
            segmentListNames.contains(candidate.getSegmentList()),
            "Candidate references an undefined segment list");
      }
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

  @JsonProperty(PROP_SEGMENT_LISTS)
  public ImmutableList<SrSegmentList> getSegmentLists() {
    return _segmentLists;
  }

  @JsonProperty(PROP_POLICIES)
  public ImmutableList<SrPolicy> getPolicies() {
    return _policies;
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
    return _vrf.equals(that._vrf)
        && _sidBindings.equals(that._sidBindings)
        && _segmentLists.equals(that._segmentLists)
        && _policies.equals(that._policies);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_vrf, _sidBindings, _segmentLists, _policies);
  }
}
