package org.batfish.minesweeper.symbolicsr;

import static com.google.common.base.Preconditions.checkArgument;
import static java.util.Objects.requireNonNull;

import javax.annotation.Nullable;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidResolver;
import org.batfish.datamodel.sr.SrSidValue;

/** One top-to-bottom MPLS stack instruction with an explicit label-resolution scope. */
public final class MplsLabelInstruction {
  public enum Scope {
    FIXED_LABEL,
    NEXT_HOP_SRGB,
    OWNER_SRLB
  }

  private final SrSidBindingKey _bindingKey;
  private final SrSidValue _configuredSid;
  private final Scope _scope;
  @Nullable private final String _ownerNode;
  @Nullable private final SrSidValue _resolvedLabel;

  static MplsLabelInstruction fixed(SrSidBindingKey key, SrSidValue label) {
    return new MplsLabelInstruction(key, label, Scope.FIXED_LABEL, null, label);
  }

  static MplsLabelInstruction nextHopSrgb(SrSidBindingKey key, SrSidValue index) {
    return new MplsLabelInstruction(key, index, Scope.NEXT_HOP_SRGB, null, null);
  }

  static MplsLabelInstruction ownerSrlb(
      SrSidBindingKey key, SrSidValue configuredSid, String ownerNode, SrSidValue label) {
    return new MplsLabelInstruction(key, configuredSid, Scope.OWNER_SRLB, ownerNode, label);
  }

  private MplsLabelInstruction(
      SrSidBindingKey bindingKey,
      SrSidValue configuredSid,
      Scope scope,
      @Nullable String ownerNode,
      @Nullable SrSidValue resolvedLabel) {
    _bindingKey = requireNonNull(bindingKey);
    _configuredSid = requireNonNull(configuredSid);
    _scope = requireNonNull(scope);
    _ownerNode = ownerNode;
    _resolvedLabel = resolvedLabel;
    checkArgument(
        (_scope == Scope.NEXT_HOP_SRGB) == (_resolvedLabel == null),
        "Only a next-hop SRGB instruction may remain unresolved");
    checkArgument(
        (_scope == Scope.OWNER_SRLB) == (_ownerNode != null),
        "Only an owner-SRLB instruction has an owner node");
    checkArgument(
        _configuredSid.getType() != SrSidValue.Type.SRV6,
        "MPLS instruction cannot contain an SRv6 SID");
    checkArgument(
        _scope != Scope.FIXED_LABEL || _configuredSid.getType() == SrSidValue.Type.MPLS_LABEL,
        "Fixed instruction requires an absolute MPLS label");
    checkArgument(
        _scope != Scope.NEXT_HOP_SRGB
            || ((_bindingKey.getType() == SrSidBindingKey.Type.PREFIX
                    || _bindingKey.getType() == SrSidBindingKey.Type.NODE)
                && _configuredSid.getType() == SrSidValue.Type.MPLS_INDEX),
        "Next-hop SRGB instruction requires a Prefix/Node SID index");
    checkArgument(
        _scope != Scope.OWNER_SRLB || _bindingKey.getType() == SrSidBindingKey.Type.ADJACENCY,
        "Owner SRLB instruction requires an adjacency SID");
    checkArgument(
        _resolvedLabel == null || _resolvedLabel.getType() == SrSidValue.Type.MPLS_LABEL,
        "Resolved SID must be an MPLS label");
  }

  public SrSidBindingKey getBindingKey() {
    return _bindingKey;
  }

  public SrSidValue getConfiguredSid() {
    return _configuredSid;
  }

  public Scope getScope() {
    return _scope;
  }

  @Nullable
  public String getOwnerNode() {
    return _ownerNode;
  }

  /** Returns a label when no next-hop-dependent resolution remains. */
  @Nullable
  public SrSidValue getResolvedLabel() {
    return _resolvedLabel;
  }

  /** Resolves this instruction for the concrete forwarding next hop. */
  public SrSidValue resolveForNextHop(Configuration nextHop) {
    requireNonNull(nextHop, "next-hop configuration must be provided");
    if (_scope != Scope.NEXT_HOP_SRGB) {
      return requireNonNull(_resolvedLabel);
    }
    SegmentRoutingConfig sr = nextHop.getSegmentRoutingConfig();
    checkArgument(
        sr != null && sr.getDataPlanes().contains(SegmentRoutingConfig.DataPlane.MPLS),
        "Next hop does not support SR-MPLS");
    return SrSidResolver.resolveMpls(_configuredSid, sr.getSrgb());
  }
}
