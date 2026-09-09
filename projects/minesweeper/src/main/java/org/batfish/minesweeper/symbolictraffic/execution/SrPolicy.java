package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nullable;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;

/**
 * One SR policy {@code P} and its weighted candidate paths, used by {@code resolveNhIp} when {@code
 * (f, nip)} matches {@code P}.
 *
 * <p>{@code g_p} is the policy-path selection guard. Forwarding to the first hop uses IGP {@code
 * VIGP} (Node-SID) or the adjacency itself (Adj-SID). The two guards are not interchangeable.
 */
public class SrPolicy {

  /** One SID in a candidate path: a Node-SID or an Adj-SID. */
  public static final class Segment {

    public enum Kind {
      NODE,
      ADJACENCY
    }

    private final Kind _kind;

    private final String _router;

    @Nullable private final String _peer;

    @Nullable private final RouteGuard _availability;

    public static Segment node(String router) {
      if (router == null || router.isEmpty()) {
        throw new IllegalArgumentException("Node-SID router cannot be null");
      }
      return new Segment(Kind.NODE, router, null, null);
    }

    public static Segment adjacency(String source, String peer) {
      return adjacency(source, peer, null);
    }

    public static Segment adjacency(
        String source, String peer, @Nullable RouteGuard availability) {
      if (source == null || source.isEmpty()) {
        throw new IllegalArgumentException("Adj-SID source router cannot be null");
      }
      if (peer == null || peer.isEmpty()) {
        throw new IllegalArgumentException("Adj-SID peer cannot be null");
      }
      return new Segment(Kind.ADJACENCY, source, peer, availability);
    }

    private Segment(
        Kind kind, String router, @Nullable String peer, @Nullable RouteGuard availability) {
      _kind = kind;
      _router = router;
      _peer = peer;
      _availability = availability;
    }

    public Kind getKind() {
      return _kind;
    }

    public boolean isAdjacency() {
      return _kind == Kind.ADJACENCY;
    }

    /** Node-SID target, or Adj-SID owner. */
    public String getRouter() {
      return _router;
    }

    @Nullable
    public String getPeer() {
      return _peer;
    }

    /**
     * Optional Adj-SID / link availability. {@code null} means always up. Direct IP next hops use
     * {@link ForwardingRule#getAvailability()} instead.
     */
    @Nullable
    public RouteGuard getAvailability() {
      return _availability;
    }

    @Override
    public boolean equals(Object o) {
      if (!(o instanceof Segment)) {
        return false;
      }
      Segment other = (Segment) o;
      return _kind == other._kind
          && _router.equals(other._router)
          && Objects.equals(_peer, other._peer)
          && Objects.equals(_availability, other._availability);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_kind, _router, _peer, _availability);
    }

    @Override
    public String toString() {
      if (_kind == Kind.NODE) {
        return "Node(" + _router + ")";
      }
      return "Adj(" + _router + "->" + _peer + ")";
    }
  }

  /** One weighted SR path {@code p} with guard {@code g_p} and stack {@code [R1, ..., Rj]}. */
  public static class Path {

    @Nullable private final String _id;

    private final RouteGuard _guard;

    private final int _weight;

    private final List<Segment> _segments;

    public Path(RouteGuard guard, int weight, List<String> nodes) {
      this(null, guard, weight, nodeSegments(nodes));
    }

    public Path(@Nullable String id, RouteGuard guard, int weight, List<Segment> segments) {
      if (guard == null) {
        throw new IllegalArgumentException("SR path guard cannot be null");
      }
      if (weight <= 0) {
        throw new IllegalArgumentException("SR path weight must be positive");
      }
      if (segments == null || segments.isEmpty()) {
        throw new IllegalArgumentException("SR path must contain a first node");
      }
      for (Segment segment : segments) {
        if (segment == null) {
          throw new IllegalArgumentException("SR path segment cannot be null");
        }
      }
      _id = id;
      _guard = guard;
      _weight = weight;
      _segments = Collections.unmodifiableList(new ArrayList<>(segments));
    }

    @Nullable
    public String getId() {
      return _id;
    }

    public RouteGuard getGuard() {
      return _guard;
    }

    public int getWeight() {
      return _weight;
    }

    public List<Segment> getSegments() {
      return _segments;
    }

    public Segment getFirstSegment() {
      return _segments.get(0);
    }

    public TrafficLabelStack toStack() {
      return new TrafficLabelStack(_segments);
    }

    private static List<Segment> nodeSegments(List<String> nodes) {
      if (nodes == null) {
        throw new IllegalArgumentException("SR path must contain a first node");
      }
      List<Segment> segments = new ArrayList<>();
      for (String node : nodes) {
        segments.add(Segment.node(node));
      }
      return segments;
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
    if (router == null || router.isEmpty()) {
      throw new IllegalArgumentException("SR policy router cannot be null");
    }
    if (endpoint == null) {
      throw new IllegalArgumentException("SR policy endpoint cannot be null");
    }
    if (paths == null || paths.isEmpty()) {
      throw new IllegalArgumentException("SR policy must contain at least one path");
    }
    _router = router;
    _endpoint = endpoint;
    _color = color;
    _name = name;
    _matchNextHop = matchNextHop;
    List<Path> copied = new ArrayList<>();
    Set<String> ids = new HashSet<>();
    for (Path path : paths) {
      if (path == null) {
        throw new IllegalArgumentException("SR path cannot be null");
      }
      if (path.getId() != null && !ids.add(path.getId())) {
        throw new IllegalArgumentException("duplicate SR path id: " + path.getId());
      }
      copied.add(path);
    }
    _paths = Collections.unmodifiableList(copied);
  }

  public String getRouter() {
    return _router;
  }

  @Nullable
  public Integer getColor() {
    return _color;
  }

  @Nullable
  public String getName() {
    return _name;
  }

  public List<Path> getPaths() {
    return _paths;
  }

  /**
   * Paper: {@code (f, nip)} matches {@code P}. A non-null policy color or name is a required field:
   * a flow with a missing color/name does not match.
   */
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
    if (_color != null && !_color.equals(flow.getColor())) {
      return false;
    }
    if (_name != null && !_name.equals(flow.getPolicy())) {
      return false;
    }
    return true;
  }

  /** Higher is more specific: named+colored beats a wildcard. */
  int matchSpecificity() {
    int specificity = 0;
    if (_color != null) {
      specificity++;
    }
    if (_name != null) {
      specificity++;
    }
    return specificity;
  }
}
