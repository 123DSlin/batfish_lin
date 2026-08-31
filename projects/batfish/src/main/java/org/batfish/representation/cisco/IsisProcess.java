package org.batfish.representation.cisco;

import java.io.Serializable;
import java.util.Map;
import java.util.TreeMap;
import javax.annotation.Nullable;
import org.batfish.datamodel.IsoAddress;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.isis.IsisLevel;

public class IsisProcess implements Serializable {

  private IsisLevel _level;

  private IsoAddress _netAddress;

  private Map<RoutingProtocol, IsisRedistributionPolicy> _redistributionPolicies;

  private boolean _segmentRoutingMpls;

  @Nullable private Long _segmentRoutingGlobalBlockStart;

  @Nullable private Long _segmentRoutingGlobalBlockEnd;

  public IsisProcess() {
    _redistributionPolicies = new TreeMap<>();
  }

  public IsisLevel getLevel() {
    return _level;
  }

  public IsoAddress getNetAddress() {
    return _netAddress;
  }

  public Map<RoutingProtocol, IsisRedistributionPolicy> getRedistributionPolicies() {
    return _redistributionPolicies;
  }

  public boolean getSegmentRoutingMpls() {
    return _segmentRoutingMpls;
  }

  @Nullable
  public Long getSegmentRoutingGlobalBlockStart() {
    return _segmentRoutingGlobalBlockStart;
  }

  @Nullable
  public Long getSegmentRoutingGlobalBlockEnd() {
    return _segmentRoutingGlobalBlockEnd;
  }

  public void setLevel(IsisLevel level) {
    _level = level;
  }

  public void setNetAddress(IsoAddress netAddress) {
    _netAddress = netAddress;
  }

  public void setSegmentRoutingMpls(boolean segmentRoutingMpls) {
    _segmentRoutingMpls = segmentRoutingMpls;
  }

  public void setSegmentRoutingGlobalBlock(long start, long end) {
    _segmentRoutingGlobalBlockStart = start;
    _segmentRoutingGlobalBlockEnd = end;
  }
}
