package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Stable, vendor-independent identity of one configured SID binding. */
@ParametersAreNonnullByDefault
public final class SrSidBindingKey implements Serializable {
  public enum Type {
    PREFIX,
    NODE,
    ADJACENCY,
    BINDING
  }

  private static final String PROP_NODE = "node";
  private static final String PROP_VRF = "vrf";
  private static final String PROP_TYPE = "type";
  private static final String PROP_ALGORITHM = "algorithm";
  private static final String PROP_PREFIX = "prefix";
  private static final String PROP_INTERFACE = "interfaceName";
  private static final String PROP_POLICY = "policyName";

  private final String _node;
  private final String _vrf;
  private final Type _type;
  private final int _algorithm;
  @Nullable private final SrPrefix _prefix;
  @Nullable private final String _interfaceName;
  @Nullable private final String _policyName;

  @JsonCreator
  public SrSidBindingKey(
      @Nullable @JsonProperty(PROP_NODE) String node,
      @Nullable @JsonProperty(PROP_VRF) String vrf,
      @Nullable @JsonProperty(PROP_TYPE) Type type,
      @JsonProperty(PROP_ALGORITHM) int algorithm,
      @Nullable @JsonProperty(PROP_PREFIX) SrPrefix prefix,
      @Nullable @JsonProperty(PROP_INTERFACE) String interfaceName,
      @Nullable @JsonProperty(PROP_POLICY) String policyName) {
    checkArgument(node != null && !node.isEmpty(), "SID owner node must be provided");
    checkArgument(vrf != null && !vrf.isEmpty(), "SID VRF must be provided");
    checkArgument(type != null, "SID binding type must be provided");
    checkArgument(algorithm >= 0 && algorithm <= 255, "SR algorithm must be an unsigned byte");
    boolean prefixType = type == Type.PREFIX || type == Type.NODE;
    checkArgument(prefixType || algorithm == 0, "Only Prefix/Node SID may select an SR algorithm");
    checkArgument(prefixType == (prefix != null), "Prefix/Node SID must have exactly one prefix");
    checkArgument(
        (type == Type.ADJACENCY) == (interfaceName != null),
        "Adjacency SID must have exactly one interface");
    checkArgument(
        interfaceName == null || !interfaceName.isEmpty(), "SID interface cannot be empty");
    checkArgument(
        (type == Type.BINDING) == (policyName != null), "Binding SID must have exactly one policy");
    checkArgument(policyName == null || !policyName.isEmpty(), "SID policy cannot be empty");
    _node = node;
    _vrf = vrf;
    _type = type;
    _algorithm = algorithm;
    _prefix = prefix;
    _interfaceName = interfaceName;
    _policyName = policyName;
  }

  @JsonProperty(PROP_NODE)
  public String getNode() {
    return _node;
  }

  @JsonProperty(PROP_VRF)
  public String getVrf() {
    return _vrf;
  }

  @JsonProperty(PROP_TYPE)
  public Type getType() {
    return _type;
  }

  @JsonProperty(PROP_ALGORITHM)
  public int getAlgorithm() {
    return _algorithm;
  }

  @Nullable
  @JsonProperty(PROP_PREFIX)
  public SrPrefix getPrefix() {
    return _prefix;
  }

  @Nullable
  @JsonProperty(PROP_INTERFACE)
  public String getInterfaceName() {
    return _interfaceName;
  }

  @Nullable
  @JsonProperty(PROP_POLICY)
  public String getPolicyName() {
    return _policyName;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof SrSidBindingKey)) return false;
    SrSidBindingKey that = (SrSidBindingKey) o;
    return _algorithm == that._algorithm
        && _node.equals(that._node)
        && _vrf.equals(that._vrf)
        && _type == that._type
        && Objects.equals(_prefix, that._prefix)
        && Objects.equals(_interfaceName, that._interfaceName)
        && Objects.equals(_policyName, that._policyName);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_node, _vrf, _type, _algorithm, _prefix, _interfaceName, _policyName);
  }
}
