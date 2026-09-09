package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.minesweeper.symbolicroute.BatfishSymbolicRoutePipelineResult;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Dual traffic-execution entry: YU Algorithm 1/2 symbolic load, and the original concrete dataplane
 * walk used by the Tolerance pipeline.
 *
 * <p>Control-plane convergence stays in {@link BatfishSymbolicRoutePipelineResult}. This class only
 * consumes that result plus a parsed {@link TrafficGraph}.
 */
public final class SymbolicTrafficPipeline {

  public static final String YU_SCHEMA = "batfish-minesweeper-symbolic-traffic-loads";

  public static final String CONCRETE_SCHEMA = "batfish-minesweeper-concrete-traffic-loads";

  public static final int SCHEMA_VERSION = 1;

  private static final int TXT_FORMULA_NODE_LIMIT = 64;

  private SymbolicTrafficPipeline() {}

  public static Result run(
      TrafficGraph graph,
      BatfishSymbolicRoutePipelineResult controlPlane,
      Map<String, Configuration> configurations,
      DataPlane dataPlane) {
    if (graph == null) {
      throw new IllegalArgumentException("traffic graph cannot be null");
    }
    SymbolicTrafficExecution.TrafficSimulation simulation =
        new SymbolicTrafficExecution(
                graph, GuardedTrafficForwarding.from(graph, controlPlane, configurations))
            .simulateAll();
    Map<TrafficGraphEdge, Double> concrete =
        ConcreteTrafficExecution.simulate(graph, dataPlane, configurations);
    return new Result(graph, simulation.getLoads(), concrete, simulation.getMatrices());
  }

  public static final class Result {
    private final TrafficGraph _graph;
    private final SymbolicTrafficLoad _yuLoads;
    private final Map<TrafficGraphEdge, Double> _concreteLoads;
    private final Map<TrafficFlow, SymbolicTrafficMatrix> _matrices;

    Result(
        TrafficGraph graph,
        SymbolicTrafficLoad yuLoads,
        Map<TrafficGraphEdge, Double> concreteLoads) {
      this(graph, yuLoads, concreteLoads, Collections.emptyMap());
    }

    Result(
        TrafficGraph graph,
        SymbolicTrafficLoad yuLoads,
        Map<TrafficGraphEdge, Double> concreteLoads,
        Map<TrafficFlow, SymbolicTrafficMatrix> matrices) {
      _graph = graph;
      _yuLoads = yuLoads;
      _concreteLoads = concreteLoads;
      _matrices = new LinkedHashMap<>(matrices);
    }

    public SymbolicTrafficLoad getYuLoads() {
      return _yuLoads;
    }

    public Map<TrafficGraphEdge, Double> getConcreteLoads() {
      return _concreteLoads;
    }

    public Map<TrafficFlow, SymbolicTrafficMatrix> getMatrices() {
      return Collections.unmodifiableMap(_matrices);
    }

    public String toYuJson() {
      Map<String, Object> root = new LinkedHashMap<>();
      root.put("schemaName", YU_SCHEMA);
      root.put("schemaVersion", SCHEMA_VERSION);
      root.put("engine", "YU_ALGORITHM_1");
      root.put("links", linkRecords(true));
      try {
        return BatfishObjectMapper.writePrettyString(root);
      } catch (Exception e) {
        throw new IllegalStateException("failed to serialize symbolic traffic loads", e);
      }
    }

    public String toConcreteJson() {
      Map<String, Object> root = new LinkedHashMap<>();
      root.put("schemaName", CONCRETE_SCHEMA);
      root.put("schemaVersion", SCHEMA_VERSION);
      root.put("engine", "CONCRETE_DATAPLANE");
      root.put("links", linkRecords(false));
      try {
        return BatfishObjectMapper.writePrettyString(root);
      } catch (Exception e) {
        throw new IllegalStateException("failed to serialize concrete traffic loads", e);
      }
    }

    /**
     * Algorithm 1 report: {@code M_f[l,S]}, then {@code Σ_S M_f[l,S]}, then {@code τ_l}. {@code
     * 0_traffic_graph.txt} is the parsed input, not this report.
     */
    public String toExecutionText() {
      StringBuilder out = new StringBuilder();
      out.append("YU ALGORITHM 1 EXECUTION\n");
      out.append("M_f[l,S] is hop-accumulated STF on real links (excludes l_R / M_0).\n");
      out.append("Per-flow STF is Σ_S M_f[l,S]. τ_l = Σ_{f,S} V_f · M_f[l,S].\n");
      int k = _graph.getMaxFailures();
      if (k < Integer.MAX_VALUE) {
        out.append("Formulas are k-failure equivalent (YU §5.2 KREDUCE, k=")
            .append(k)
            .append(").\n");
      }
      out.append("AllUp evaluates every guard variable as true (no failures).\n");
      appendMatrix(out);
      appendFlowStf(out);
      appendTau(out);
      return out.toString();
    }

    private void appendMatrix(StringBuilder out) {
      out.append("\n=== M_f[l, S] ===\n");
      out.append(
          String.format(
              "%-16s %-8s %-8s %-8s %-28s %-12s %s%n",
              "Flow", "Link", "Router", "Peer", "Stack", "AllUp", "Formula"));
      out.append(
          "================================================================================================\n");
      if (_matrices.isEmpty()) {
        out.append("(no per-flow matrices)\n");
        return;
      }
      for (Map.Entry<TrafficFlow, SymbolicTrafficMatrix> entry : _matrices.entrySet()) {
        TrafficFlow flow = entry.getKey();
        SymbolicTrafficMatrix matrix = entry.getValue();
        boolean any = false;
        for (TrafficGraphEdge edge : sortedRealEdges(matrix.edges())) {
          List<TrafficLabelStack> stacks = new ArrayList<>(matrix.stacks(edge));
          stacks.sort((a, b) -> a.toString().compareTo(b.toString()));
          for (TrafficLabelStack stack : stacks) {
            SymbolicTrafficFraction cell = matrix.get(edge, stack);
            if (cell.isZero()) {
              continue;
            }
            any = true;
            appendCell(out, flow.getId(), edge, formatStack(stack), cell);
          }
        }
        if (!any) {
          out.append(String.format("%-16s (no real-link cells)%n", flow.getId()));
        }
      }
    }

    private void appendFlowStf(StringBuilder out) {
      out.append("\n=== Per-flow link STF  Σ_S M_f[l,S] ===\n");
      out.append(
          String.format(
              "%-16s %-8s %-8s %-8s %-12s %s%n",
              "Flow", "Link", "Router", "Peer", "AllUp", "Formula"));
      out.append(
          "================================================================================\n");
      if (_matrices.isEmpty()) {
        out.append("(no per-flow matrices)\n");
        return;
      }
      for (Map.Entry<TrafficFlow, SymbolicTrafficMatrix> entry : _matrices.entrySet()) {
        TrafficFlow flow = entry.getKey();
        SymbolicTrafficMatrix matrix = entry.getValue();
        boolean any = false;
        for (TrafficGraphEdge edge : sortedRealEdges(matrix.edges())) {
          SymbolicTrafficFraction stf = SymbolicTrafficFraction.zero();
          for (TrafficLabelStack stack : matrix.stacks(edge)) {
            stf = stf.plus(matrix.get(edge, stack));
          }
          if (stf.isZero()) {
            continue;
          }
          any = true;
          appendCell(out, flow.getId(), edge, null, stf);
        }
        if (!any) {
          out.append(String.format("%-16s (no real-link STF)%n", flow.getId()));
        }
      }
    }

    private void appendTau(StringBuilder out) {
      out.append("\n=== τ_l = Σ_{f,S} V_f · M_f[l,S] ===\n");
      out.append(
          String.format(
              "%-8s %-8s %-8s %-12s %-12s %s%n",
              "Link", "Router", "Peer", "CapGbps", "AllUp", "Formula"));
      out.append(
          "================================================================================\n");
      for (TrafficGraphEdge edge : sortedRealEdges(_graph.getEdges())) {
        SymbolicTrafficFraction tau = _yuLoads.get(edge);
        out.append(
            String.format(
                "%-8s %-8s %-8s %-12s %-12s %s%n",
                edge.getId(),
                edge.getRouter(),
                nullToDash(edge.getPeer()),
                formatDouble(edge.getCapacityGbps()),
                formatDouble(tau.evaluateAllUp()),
                tau.toDisplayString(TXT_FORMULA_NODE_LIMIT)));
      }
    }

    private void appendCell(
        StringBuilder out,
        String flowId,
        TrafficGraphEdge edge,
        String stack,
        SymbolicTrafficFraction value) {
      if (stack == null) {
        out.append(
            String.format(
                "%-16s %-8s %-8s %-8s %-12s %s%n",
                flowId,
                edge.getId(),
                edge.getRouter(),
                nullToDash(edge.getPeer()),
                formatDouble(value.evaluateAllUp()),
                value.toDisplayString(TXT_FORMULA_NODE_LIMIT)));
        return;
      }
      out.append(
          String.format(
              "%-16s %-8s %-8s %-8s %-28s %-12s %s%n",
              flowId,
              edge.getId(),
              edge.getRouter(),
              nullToDash(edge.getPeer()),
              stack,
              formatDouble(value.evaluateAllUp()),
              value.toDisplayString(TXT_FORMULA_NODE_LIMIT)));
    }

    private java.util.List<Map<String, Object>> linkRecords(boolean yu) {
      java.util.List<Map<String, Object>> links = new java.util.ArrayList<>();
      for (TrafficGraphEdge edge : sortedRealEdges(_graph.getEdges())) {
        Map<String, Object> row = new TreeMap<>();
        row.put("id", edge.getId());
        row.put("router", edge.getRouter());
        row.put("peer", edge.getPeer());
        row.put("capacityGbps", edge.getCapacityGbps());
        if (yu) {
          SymbolicTrafficFraction tau = _yuLoads.get(edge);
          row.put("tau", tau.toJsonValue());
        } else {
          row.put("loadGbps", _concreteLoads.getOrDefault(edge, 0.0));
        }
        links.add(row);
      }
      return links;
    }

    private static List<TrafficGraphEdge> sortedRealEdges(Iterable<TrafficGraphEdge> edges) {
      List<TrafficGraphEdge> sorted = new ArrayList<>();
      for (TrafficGraphEdge edge : edges) {
        if (!edge.isPseudoIncoming()) {
          sorted.add(edge);
        }
      }
      sorted.sort(
          (a, b) -> {
            int id = a.getId().compareTo(b.getId());
            if (id != 0) {
              return id;
            }
            return a.getRouter().compareTo(b.getRouter());
          });
      return sorted;
    }

    private static String formatStack(TrafficLabelStack stack) {
      if (stack.isEmpty()) {
        return "[]";
      }
      return stack.toString();
    }

    private static String nullToDash(String value) {
      return value == null ? "-" : value;
    }

    private static String formatDouble(double value) {
      if (value == Math.rint(value) && !Double.isInfinite(value)) {
        return String.format("%.1f", value);
      }
      return String.format("%.6f", value);
    }
  }
}
