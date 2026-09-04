package org.batfish.minesweeper.symbolictraffic.parse;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nullable;
import org.batfish.common.NetworkSnapshot;
import org.batfish.common.plugin.IBatfish;
import org.batfish.datamodel.Configuration;

/**
 * Parsed traffic topology, analogous to {@link org.batfish.minesweeper.Graph}.
 *
 * <p>This class owns traffic-layer parsing: {@code traffic.json} and, later, Batfish snapshot
 * topology. {@code org.batfish.minesweeper.symbolictraffic.execution} consumes the resulting
 * objects and must not parse files or configurations.
 */
public class TrafficGraph {

  private final Set<String> _routers;

  private final List<TrafficGraphEdge> _edges;

  private final List<TrafficFlow> _flows;

  private final Map<String, List<TrafficGraphEdge>> _edgeMap;

  private final Map<TrafficGraphEdge, TrafficGraphEdge> _otherEnd;

  /**
   * In-memory graph already produced by a parser. Callers that load configs or JSON should use the
   * static factories rather than assembling edges by hand, except in tests.
   */
  public TrafficGraph(
      Collection<String> routers,
      Collection<TrafficGraphEdge> edges,
      Collection<TrafficFlow> flows) {
    _routers = new HashSet<>(routers);
    _edges = new ArrayList<>(edges);
    _flows = new ArrayList<>(flows);
    _edgeMap = new HashMap<>();
    _otherEnd = new HashMap<>();
    for (TrafficGraphEdge edge : _edges) {
      _edgeMap.computeIfAbsent(edge.getRouter(), unused -> new ArrayList<>()).add(edge);
      _routers.add(edge.getRouter());
      if (edge.getPeer() != null) {
        _routers.add(edge.getPeer());
      }
    }
    for (TrafficFlow flow : _flows) {
      _routers.add(flow.getSource());
    }
  }

  /** Parse a traffic.json demand/capacity file. Not implemented. */
  public static TrafficGraph fromTrafficJson(Path path) {
    throw new UnsupportedOperationException(
        "traffic.json parsing is not implemented yet: " + path);
  }

  /**
   * Parse topology from a Batfish snapshot the same way {@link org.batfish.minesweeper.Graph} does.
   * Not implemented.
   */
  public static TrafficGraph fromBatfish(IBatfish batfish, NetworkSnapshot snapshot) {
    throw new UnsupportedOperationException(
        "Batfish traffic-graph parsing is not implemented yet: " + batfish + " " + snapshot);
  }

  /**
   * Parse topology from already-cloned vendor-independent configs. Not implemented.
   *
   * @param configs same contract as {@link org.batfish.minesweeper.Graph}: may be mutated; callers
   *     should copy first if they need the original map
   */
  public static TrafficGraph fromConfigurations(
      IBatfish batfish,
      NetworkSnapshot snapshot,
      @Nullable Map<String, Configuration> configs) {
    throw new UnsupportedOperationException(
        "configuration traffic-graph parsing is not implemented yet: "
            + snapshot
            + " batfish="
            + batfish
            + " configs="
            + configs);
  }

  public Set<String> getRouters() {
    return _routers;
  }

  public List<TrafficGraphEdge> getEdges() {
    return _edges;
  }

  public List<TrafficFlow> getFlows() {
    return _flows;
  }

  public List<TrafficGraphEdge> getIncomingEdges(String router) {
    List<TrafficGraphEdge> incoming = new ArrayList<>();
    for (TrafficGraphEdge edge : _edges) {
      if (router.equals(edge.getPeer())
          || (edge.isPseudoIncoming() && router.equals(edge.getRouter()))) {
        incoming.add(edge);
      }
    }
    return incoming;
  }

  public List<TrafficGraphEdge> getOutgoingEdges(String router) {
    List<TrafficGraphEdge> outgoing = _edgeMap.get(router);
    if (outgoing == null) {
      return new ArrayList<>();
    }
    return new ArrayList<>(outgoing);
  }

  @Nullable
  public TrafficGraphEdge getOtherEnd(TrafficGraphEdge edge) {
    return _otherEnd.get(edge);
  }
}
