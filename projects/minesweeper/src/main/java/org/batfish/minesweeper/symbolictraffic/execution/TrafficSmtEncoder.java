package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Traffic SMT encoding parallel to reachability {@code smt_encoding.smt2}. It directly serializes
 * Algorithm 1's symbolic {@code tau_l}, retaining link-aliveness Booleans and SR weight variables.
 *
 * <p>Weight domain (RFC 9256 / Batfish {@code SrCandidatePath}):
 *
 * <ul>
 *   <li>Default is 1 when CLI omits weight (RFC 9256 §2.2; extractor uses {@code weight == null ?
 *       1}).
 *   <li>Weight 0 is invalid encoding (not “steer zero traffic”); rejected at convert time.
 *   <li>Negative weights are not representable; SMT domain is {@code 1 .. 2^32-1}.
 * </ul>
 */
public final class TrafficSmtEncoder {

  public static final String SMT_FILE_NAME = "smt_traffic_encoding.smt2";

  private TrafficSmtEncoder() {}

  /** Encode the Algorithm 1 result directly, preserving both failure and configuration symbols. */
  public static String encodeSymbolic(TrafficGraph graph, SymbolicTrafficLoad yuLoads) {
    if (graph == null) {
      throw new IllegalArgumentException("traffic graph cannot be null");
    }
    if (yuLoads == null) {
      throw new IllegalArgumentException("YU loads cannot be null");
    }
    Map<String, Integer> weightPins = new TreeMap<>();
    java.util.Set<String> guardVariables = new java.util.TreeSet<>();
    for (SymbolicTrafficFraction load : yuLoads.getLoads().values()) {
      load.collectWeights(weightPins);
      guardVariables.addAll(load.getGuardVariables());
    }

    List<TrafficGraphEdge> edges = sortedRealEdges(graph.getEdges());
    StringBuilder out = new StringBuilder();
    out.append("; Symbolic Traffic SMT encoding (parallel to reachability smt_encoding.smt2)\n");
    out.append("; Direct serialization of YU Algorithm 1 tau_l expressions.\n");
    out.append("; SpecLens: comment (= Config_*_weight <pin>) to unpin SR candidate weights.\n\n");

    for (String variable : guardVariables) {
      out.append("(declare-fun ").append(variable).append(" () Bool)\n");
    }
    if (!guardVariables.isEmpty()) {
      out.append('\n');
    }
    int k = graph.getMaxFailures();
    if (k < Integer.MAX_VALUE && !guardVariables.isEmpty()) {
      out.append("(assert (<= (+");
      for (String variable : guardVariables) {
        out.append(" (ite ").append(variable).append(" 0 1)");
      }
      out.append(") ").append(k).append("))\n\n");
    }

    // Same shape as Minesweeper Config_*: declare-fun, then (= pin), then domain bounds.
    for (Map.Entry<String, Integer> entry : weightPins.entrySet()) {
      String var = entry.getKey();
      out.append("(declare-fun ")
          .append(var)
          .append("\n")
          .append("             ()\n")
          .append("             Int)\n");
    }
    if (!weightPins.isEmpty()) {
      out.append('\n');
    }
    for (Map.Entry<String, Integer> entry : weightPins.entrySet()) {
      String var = entry.getKey();
      int pin = entry.getValue();
      out.append("(assert (= ").append(var).append(' ').append(pin).append("))\n");
      // Domain: positive uint32. RFC 9256 default=1 (omit→1); weight 0 invalid; no negatives.
      out.append("(assert (>= ").append(var).append(" 1))\n");
      out.append("(assert (<= ").append(var).append(" 4294967295))\n");
    }
    if (!weightPins.isEmpty()) {
      out.append('\n');
    }

    for (TrafficGraphEdge edge : edges) {
      SymbolicTrafficFraction load = yuLoads.get(edge);
      double yuAllUp = load.evaluateAllUp();
      String loadExpr = load.toSmtReal();
      String loadVar = loadName(edge);

      out.append("; link ")
          .append(edge.getId())
          .append(' ')
          .append(edge.getRouter())
          .append(" -> ")
          .append(edge.getPeer() == null ? "-" : edge.getPeer())
          .append(" cap=")
          .append(formatReal(edge.getCapacityGbps()))
          .append(" yuAllUp=")
          .append(formatReal(yuAllUp))
          .append('\n');
      out.append("(declare-fun ")
          .append(loadVar)
          .append("\n")
          .append("             ()\n")
          .append("             Real)\n");
      out.append("(assert (= ").append(loadVar).append(' ').append(loadExpr).append("))\n");
      out.append("(assert (< ")
          .append(loadVar)
          .append(' ')
          .append(formatReal(edge.getCapacityGbps()))
          .append("))\n\n");
    }

    out.append("(check-sat)\n");
    // Match reachability encoding style.
    out.append(";(get-model)\n");
    return out.toString();
  }

  private static String loadName(TrafficGraphEdge edge) {
    String peer = edge.getPeer() == null ? "none" : edge.getPeer();
    return "load_"
        + sanitize(edge.getId())
        + "_"
        + sanitize(edge.getRouter())
        + "_"
        + sanitize(peer);
  }

  private static String sanitize(String raw) {
    StringBuilder out = new StringBuilder();
    for (char c : raw.toCharArray()) {
      if (Character.isLetterOrDigit(c) || c == '_') {
        out.append(c);
      } else {
        out.append('_');
      }
    }
    return out.toString();
  }

  private static String formatReal(double value) {
    if (Double.isNaN(value) || Double.isInfinite(value)) {
      throw new IllegalArgumentException("non-finite real");
    }
    if (value == Math.rint(value)) {
      return Long.toString(Math.round(value)) + ".0";
    }
    return Double.toString(value);
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
}
