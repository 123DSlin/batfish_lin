package org.batfish.minesweeper.symbolictraffic.parse;

import com.fasterxml.jackson.databind.JsonNode;
import java.io.IOException;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import javax.annotation.Nullable;
import org.batfish.common.NetworkSnapshot;
import org.batfish.common.plugin.IBatfish;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Prefix;
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
   * YU {@code k}: at most this many simultaneous undirected-link failures. {@link
   * Integer#MAX_VALUE} means Algorithm 1 does not apply {@code k}-failure reduction.
   */
  private final int _maxFailures;

  /**
   * In-memory graph already produced by a parser. Callers that load configs or JSON should use the
   * static factories rather than assembling edges by hand, except in tests.
   */
  public TrafficGraph(
      Collection<String> routers,
      Collection<TrafficGraphEdge> edges,
      Collection<TrafficFlow> flows) {
    this(routers, edges, flows, Integer.MAX_VALUE);
  }

  public TrafficGraph(
      Collection<String> routers,
      Collection<TrafficGraphEdge> edges,
      Collection<TrafficFlow> flows,
      int maxFailures) {
    if (maxFailures < 0) {
      throw new IllegalArgumentException("maxFailures cannot be negative");
    }
    _maxFailures = maxFailures;
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
    for (TrafficGraphEdge edge : _edges) {
      if (edge.isPseudoIncoming()) {
        continue;
      }
      for (TrafficGraphEdge other : _edges) {
        if (other == edge || other.isPseudoIncoming()) {
          continue;
        }
        if (edge.getId().equals(other.getId())
            && edge.getRouter().equals(other.getPeer())
            && edge.getPeer() != null
            && edge.getPeer().equals(other.getRouter())) {
          _otherEnd.put(edge, other);
          break;
        }
      }
    }
  }

  /** Parse a traffic.json demand/capacity file. */
  public static TrafficGraph fromTrafficJson(Path path) {
    try {
      JsonNode root = BatfishObjectMapper.mapper().readTree(Files.newBufferedReader(path));

      Set<String> routers = new HashSet<>();
      List<TrafficGraphEdge> edges = new ArrayList<>();
      List<TrafficFlow> flows = new ArrayList<>();
      Set<String> linkIds = new HashSet<>();
      Set<String> flowIds = new HashSet<>();
      int maxFailures = readMaxFailures(root.get("failureModel"));

      JsonNode linksNode = root.get("links");
      if (linksNode == null || !linksNode.isArray()) {
        throw new IllegalArgumentException("traffic.json must contain an array named links");
      }

      for (JsonNode link : linksNode) {
        String id = getTextField(link, "id");
        if (!linkIds.add(id)) {
          throw new IllegalArgumentException("duplicate link id: " + id);
        }
        double capacity = getDoubleField(link, "capacityGbps");
        JsonNode e1 = link.get("endpoint1");
        JsonNode e2 = link.get("endpoint2");
        if (e1 == null || e2 == null) {
          throw new IllegalArgumentException("each link must have endpoint1 and endpoint2: " + id);
        }
        String node1 = getTextField(e1, "node");
        String node2 = getTextField(e2, "node");
        String iface1 = getTextField(e1, "interface");
        String iface2 = getTextField(e2, "interface");

        routers.add(node1);
        routers.add(node2);
        TrafficGraphEdge edge12 =
            new TrafficGraphEdge(id, node1, node2, iface1, iface2, capacity, false);
        TrafficGraphEdge edge21 =
            new TrafficGraphEdge(id, node2, node1, iface2, iface1, capacity, false);
        edges.add(edge12);
        edges.add(edge21);
      }

      JsonNode flowsNode = root.get("flows");
      if (flowsNode != null) {
        if (!flowsNode.isArray()) {
          throw new IllegalArgumentException("traffic.json flows must be an array");
        }
        for (JsonNode flow : flowsNode) {
          String id = getTextField(flow, "id");
          if (!flowIds.add(id)) {
            throw new IllegalArgumentException("duplicate flow id: " + id);
          }
          String forwarding = getTextField(flow, "forwarding");
          flows.add(
              new TrafficFlow(
                  id,
                  getTextField(flow, "source"),
                  Prefix.parse(getTextField(flow, "destination")),
                  getDoubleField(flow, "demandGbps"),
                  TrafficFlow.parseForwardingType(forwarding),
                  readOptionalInt(flow, "color"),
                  readOptionalText(flow, "policy")));
        }
      }
      return new TrafficGraph(routers, edges, flows, maxFailures);
    } catch (IOException e) {
      throw new IllegalArgumentException("failed to read traffic json: " + path, e);
    }
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
    return Collections.unmodifiableSet(_routers);
  }

  private static String getTextField(JsonNode node, String field) {
    JsonNode child = node.get(field);
    if (child == null || !child.isTextual()) {
      throw new IllegalArgumentException("missing textual field: " + field);
    }
    return child.textValue();
  }

  private static double getDoubleField(JsonNode node, String field) {
    JsonNode child = node.get(field);
    if (child == null || !child.isNumber()) {
      throw new IllegalArgumentException("missing numeric field: " + field);
    }
    return child.doubleValue();
  }

  private static @Nullable Integer readOptionalInt(JsonNode node, String field) {
    JsonNode child = node.get(field);
    if (child == null) {
      return null;
    }
    if (!child.isIntegralNumber()) {
      throw new IllegalArgumentException("invalid integer field: " + field);
    }
    return child.intValue();
  }

  private static @Nullable String readOptionalText(JsonNode node, String field) {
    JsonNode child = node.get(field);
    return child == null ? null : child.textValue();
  }

  private static int readMaxFailures(@Nullable JsonNode failureModel) {
    if (failureModel == null || failureModel.isNull()) {
      return Integer.MAX_VALUE;
    }
    JsonNode max = failureModel.get("maxFailures");
    if (max == null || max.isNull()) {
      return Integer.MAX_VALUE;
    }
    if (!max.isIntegralNumber()) {
      throw new IllegalArgumentException("failureModel.maxFailures must be an integer");
    }
    int value = max.intValue();
    if (value < 0) {
      throw new IllegalArgumentException("failureModel.maxFailures cannot be negative");
    }
    return value;
  }

  public List<TrafficGraphEdge> getEdges() {
    return Collections.unmodifiableList(_edges);
  }

  public List<TrafficFlow> getFlows() {
    return Collections.unmodifiableList(_flows);
  }

  /**
   * Maximum simultaneous undirected-link failures considered by TLP / {@code k}-failure reduction.
   * Missing {@code failureModel} in {@code traffic.json} leaves this unbounded.
   */
  public int getMaxFailures() {
    return _maxFailures;
  }

  /** Parsed {@code traffic.json} dump for {@code 0_traffic_graph.txt}. */
  public String toInputText() {
    StringBuilder out = new StringBuilder();
    out.append("Parsed traffic.json (input topology and flows).\n");
    out.append("Algorithm 1 output is 0_symbolic_traffic_execution.txt.\n\n");
    out.append("Traffic Graph\nRouters:\n");
    List<String> routers = new ArrayList<>(_routers);
    Collections.sort(routers);
    for (String router : routers) {
      out.append("  ").append(router).append('\n');
    }
    out.append("\nLinks:\n");
    for (TrafficGraphEdge edge : getEdges()) {
      if (edge.isPseudoIncoming()) {
        continue;
      }
      out.append("  ")
          .append(edge.getId())
          .append(' ')
          .append(edge.getRouter())
          .append(" -> ")
          .append(edge.getPeer() == null ? "-" : edge.getPeer())
          .append(" cap=")
          .append(edge.getCapacityGbps())
          .append(" iface=")
          .append(edge.getStartInterface() == null ? "-" : edge.getStartInterface())
          .append('@')
          .append(edge.getEndInterface() == null ? "-" : edge.getEndInterface())
          .append('\n');
    }
    out.append("\nFlows:\n");
    for (TrafficFlow flow : _flows) {
      out.append("  ")
          .append(flow.getId())
          .append(" src=")
          .append(flow.getSource())
          .append(" dst=")
          .append(flow.getDestination())
          .append(" demandGbps=")
          .append(flow.getDemandGbps())
          .append(" forwarding=")
          .append(flow.getForwarding())
          .append('\n');
    }
    return out.toString();
  }

  /**
   * Undirected link ids, the Boolean variables {@code x_l} in YU (1 = up). Algorithm 1 reduces
   * STFs to be {@code k}-failure equivalent over this set.
   */
  public List<String> getFailureVariables() {
    Set<String> ids = new TreeSet<>();
    for (TrafficGraphEdge edge : _edges) {
      if (!edge.isPseudoIncoming()) {
        ids.add(edge.getId());
      }
    }
    return new ArrayList<>(ids);
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
