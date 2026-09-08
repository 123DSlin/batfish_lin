package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.List;
import javax.annotation.Nullable;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;

/**
 * One SR policy {@code P} and its weighted candidate paths, used by {@code resolveNhIp} when {@code
 * (f, nip)} matches {@code P}.
 */
public class SrPolicy {

  /** One weighted SR path {@code p} with guard {@code g_p} and stack {@code [R1, ..., Rj]}. */
  public static class Path {

    private final RouteGuard _guard;

    private final int _weight;

    private final List<String> _nodes;

    public Path(RouteGuard guard, int weight, List<String> nodes) {
      _guard = guard;
      _weight = weight;
      _nodes = new ArrayList<>(nodes);
    }

    public RouteGuard getGuard() {
      return _guard;
    }

    public int getWeight() {
      return _weight;
    }

    public List<String> getNodes() {
      return _nodes;
    }

    public String getFirstNode() {
      return _nodes.get(0);
    }

    public TrafficLabelStack toStack() {
      return new TrafficLabelStack(_nodes);
    }
  }

  private final String _router;

  private final Prefix _endpoint;

  @Nullable private final Integer _color;

  @Nullable private final String _name;

  @Nullable private final Ip _matchNextHop;

  private final List<Path> _paths;

  public SrPolicy(
      String router,
      Prefix endpoint,
      @Nullable Integer color,
      @Nullable String name,
      @Nullable Ip matchNextHop,
      List<Path> paths) {
    _router = router;
    _endpoint = endpoint;
    _color = color;
    _name = name;
    _matchNextHop = matchNextHop;
    _paths = new ArrayList<>(paths);
  }

  public String getRouter() {
    return _router;
  }

  public List<Path> getPaths() {
    return _paths;
  }

  /** Paper: {@code (f, nip)} matches {@code P}. */
  public boolean matches(String router, TrafficFlow flow, Ip nextHopIp) {
    if (!_router.equals(router)) {
      return false;
    }
    if (!_endpoint.containsIp(flow.getDestination().getStartIp())) {
      return false;
    }
    if (_matchNextHop != null && !_matchNextHop.equals(nextHopIp)) {
      return false;
    }
    if (_color != null && flow.getColor() != null && !_color.equals(flow.getColor())) {
      return false;
    }
    if (_name != null && flow.getPolicy() != null && !_name.equals(flow.getPolicy())) {
      return false;
    }
    return true;
  }
}
