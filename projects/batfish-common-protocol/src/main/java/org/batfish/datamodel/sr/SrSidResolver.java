package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Resolves configured SID values without changing their stable binding identity. */
@ParametersAreNonnullByDefault
public final class SrSidResolver {
  private SrSidResolver() {}

  /** Resolves an absolute label or SRGB-relative index to the on-wire MPLS label. */
  public static SrSidValue resolveMpls(SrSidValue sid, @Nullable SrGlobalBlock srgb) {
    if (sid.getType() == SrSidValue.Type.MPLS_LABEL) {
      return sid;
    }
    checkArgument(sid.getType() == SrSidValue.Type.MPLS_INDEX, "SID is not an MPLS value");
    checkArgument(srgb != null, "Cannot resolve an MPLS index without an SRGB");
    return srgb.resolve(sid);
  }

  /** Resolves an absolute local label or SRLB-relative adjacency/binding SID index. */
  public static SrSidValue resolveLocalMpls(SrSidValue sid, @Nullable SrLocalBlock srlb) {
    if (sid.getType() == SrSidValue.Type.MPLS_LABEL) {
      return sid;
    }
    checkArgument(sid.getType() == SrSidValue.Type.MPLS_INDEX, "SID is not an MPLS value");
    checkArgument(srlb != null, "Cannot resolve a local MPLS index without an SRLB");
    return srlb.resolve(sid);
  }
}
