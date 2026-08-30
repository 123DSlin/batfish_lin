package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.io.Serializable;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Device-level vendor-independent Segment Routing configuration. */
@ParametersAreNonnullByDefault
public final class SegmentRoutingConfig implements Serializable {
  public enum DataPlane {
    MPLS,
    SRV6
  }

  private static final String PROP_DATA_PLANES = "dataPlanes";
  private static final String PROP_SRGB = "srgb";
  private static final String PROP_SRLB = "srlb";
  private static final String PROP_VRFS = "vrfs";

  private final ImmutableSet<DataPlane> _dataPlanes;
  @Nullable private final SrGlobalBlock _srgb;
  @Nullable private final SrLocalBlock _srlb;
  private final ImmutableMap<String, SegmentRoutingVrfConfig> _vrfs;

  @JsonCreator
  public SegmentRoutingConfig(
      @Nullable @JsonProperty(PROP_DATA_PLANES) Set<DataPlane> dataPlanes,
      @Nullable @JsonProperty(PROP_SRGB) SrGlobalBlock srgb,
      @Nullable @JsonProperty(PROP_SRLB) SrLocalBlock srlb,
      @Nullable @JsonProperty(PROP_VRFS) Map<String, SegmentRoutingVrfConfig> vrfs) {
    _dataPlanes = dataPlanes == null ? ImmutableSet.of() : ImmutableSet.copyOf(dataPlanes);
    _srgb = srgb;
    _srlb = srlb;
    _vrfs = vrfs == null ? ImmutableMap.of() : ImmutableMap.copyOf(vrfs);
    checkArgument(!_dataPlanes.isEmpty(), "At least one SR data plane must be enabled");
    checkArgument(_dataPlanes.contains(DataPlane.MPLS) || srgb == null, "SRGB requires SR-MPLS");
    checkArgument(_dataPlanes.contains(DataPlane.MPLS) || srlb == null, "SRLB requires SR-MPLS");
    _vrfs.forEach(
        (name, config) -> checkArgument(name.equals(config.getVrf()), "SR VRF map key mismatch"));
  }

  @JsonProperty(PROP_DATA_PLANES)
  public ImmutableSet<DataPlane> getDataPlanes() {
    return _dataPlanes;
  }

  @Nullable
  @JsonProperty(PROP_SRGB)
  public SrGlobalBlock getSrgb() {
    return _srgb;
  }

  @Nullable
  @JsonProperty(PROP_SRLB)
  public SrLocalBlock getSrlb() {
    return _srlb;
  }

  @JsonProperty(PROP_VRFS)
  public ImmutableMap<String, SegmentRoutingVrfConfig> getVrfs() {
    return _vrfs;
  }

  /** Validates device ownership after this config is attached to a Batfish Configuration. */
  public void validateOwner(String hostname) {
    _vrfs.values().stream()
        .flatMap(vrf -> vrf.getSidBindings().stream())
        .forEach(
            binding ->
                checkArgument(
                    binding.getKey().getNode().equals(hostname),
                    "SID binding owner does not match Configuration hostname"));
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SegmentRoutingConfig)) {
      return false;
    }
    SegmentRoutingConfig that = (SegmentRoutingConfig) object;
    return _dataPlanes.equals(that._dataPlanes)
        && Objects.equals(_srgb, that._srgb)
        && Objects.equals(_srlb, that._srlb)
        && _vrfs.equals(that._vrfs);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_dataPlanes, _srgb, _srlb, _vrfs);
  }
}
