package org.batfish.representation.cisco;

import java.io.Serializable;
import java.util.SortedMap;
import java.util.TreeMap;
import javax.annotation.ParametersAreNonnullByDefault;

/** Cisco SR-TE segment list whose entries are explicit MPLS labels. */
@ParametersAreNonnullByDefault
public final class CiscoSrSegmentList implements Serializable {
  private final String _name;
  private final SortedMap<Long, Long> _labels;

  public CiscoSrSegmentList(String name) {
    _name = name;
    _labels = new TreeMap<>();
  }

  public String getName() {
    return _name;
  }

  public SortedMap<Long, Long> getLabels() {
    return _labels;
  }
}
