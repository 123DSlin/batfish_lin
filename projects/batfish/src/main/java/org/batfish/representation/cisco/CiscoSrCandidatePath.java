package org.batfish.representation.cisco;

import java.io.Serializable;
import javax.annotation.ParametersAreNonnullByDefault;

/** Explicit Cisco SR-TE candidate path. */
@ParametersAreNonnullByDefault
public final class CiscoSrCandidatePath implements Serializable {
  private final long _preference;
  private final long _weight;
  private final String _segmentList;

  public CiscoSrCandidatePath(long preference, long weight, String segmentList) {
    _preference = preference;
    _weight = weight;
    _segmentList = segmentList;
  }

  public long getPreference() {
    return _preference;
  }

  public long getWeight() {
    return _weight;
  }

  public String getSegmentList() {
    return _segmentList;
  }

  /** Identity excludes mutable preference and weight by design. */
  public String stableIdentity() {
    return "explicit:" + _segmentList;
  }
}
