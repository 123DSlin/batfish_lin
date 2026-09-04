package org.batfish.minesweeper.symbolictraffic.parse;

import java.util.Objects;
import javax.annotation.Nullable;

/**
 * A directed traffic edge, analogous to {@link org.batfish.minesweeper.GraphEdge}.
 *
 * <p>Concrete edges correspond to topology links. A pseudo incoming edge has {@code peer == null}
 * and is used by YU Algorithm 1 as {@code l_R}, the fictitious ingress into the flow's receiving
 * router.
 */
public class TrafficGraphEdge {

  private final String _id;

  private final String _router;

  @Nullable private final String _peer;

  @Nullable private final String _startInterface;

  @Nullable private final String _endInterface;

  private final double _capacityGbps;

  private final boolean _isPseudoIncoming;

  public TrafficGraphEdge(
      String id,
      String router,
      @Nullable String peer,
      @Nullable String startInterface,
      @Nullable String endInterface,
      double capacityGbps,
      boolean isPseudoIncoming) {
    _id = id;
    _router = router;
    _peer = isPseudoIncoming ? null : peer;
    _startInterface = startInterface;
    _endInterface = _peer == null ? null : endInterface;
    _capacityGbps = capacityGbps;
    _isPseudoIncoming = isPseudoIncoming;
  }

  public String getId() {
    return _id;
  }

  public String getRouter() {
    return _router;
  }

  @Nullable
  public String getPeer() {
    return _peer;
  }

  @Nullable
  public String getStartInterface() {
    return _startInterface;
  }

  @Nullable
  public String getEndInterface() {
    return _endInterface;
  }

  public double getCapacityGbps() {
    return _capacityGbps;
  }

  public boolean isPseudoIncoming() {
    return _isPseudoIncoming;
  }

  @Override
  public boolean equals(Object o) {
    if (!(o instanceof TrafficGraphEdge)) {
      return false;
    }
    TrafficGraphEdge other = (TrafficGraphEdge) o;
    return _isPseudoIncoming == other._isPseudoIncoming
        && Double.compare(_capacityGbps, other._capacityGbps) == 0
        && Objects.equals(_id, other._id)
        && Objects.equals(_router, other._router)
        && Objects.equals(_peer, other._peer)
        && Objects.equals(_startInterface, other._startInterface)
        && Objects.equals(_endInterface, other._endInterface);
  }

  @Override
  public int hashCode() {
    return Objects.hash(
        _id, _router, _peer, _startInterface, _endInterface, _capacityGbps, _isPseudoIncoming);
  }

  @Override
  public String toString() {
    if (_isPseudoIncoming) {
      return "pseudo-ingress->" + _router;
    }
    return _router + "->" + _peer + "[" + _id + "]";
  }
}
