package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import javax.annotation.Nullable;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Traffic SMT encoding parallel to reachability {@code smt_encoding.smt2}. Does <em>not</em> alter
 * YU Algorithm 1: it only reads AllUp τ numbers plus SR policies and emits SpecLens {@code
 * Config_*_weight} pins in the same declare/assert style as Minesweeper Config encoding.
 *
 * <p>Scenario is AllUp (no failures). SR candidate shares are {@code w_p / Σ w}; IP contribution on
 * each link is {@code τ_YU(AllUp) − SR_pinned(AllUp)} so the concrete AllUp load is preserved when
 * weights stay at their cfg pins.
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

  /**
   * Build {@code smt_traffic_encoding.smt2} from YU AllUp loads and SR policies. Independent of
   * Algorithm 1's internal fraction DAG.
   */
  public static String encodeAllUp(
      TrafficGraph graph,
      SymbolicTrafficLoad yuLoads,
      Map<String, List<SrPolicy>> srPolicies) {
    if (graph == null) {
      throw new IllegalArgumentException("traffic graph cannot be null");
    }
    if (yuLoads == null) {
      throw new IllegalArgumentException("YU loads cannot be null");
    }
    if (srPolicies == null) {
      srPolicies = java.util.Collections.emptyMap();
    }

    Map<String, Integer> weightPins = collectWeightPins(srPolicies);
    Map<TrafficGraphEdge, Double> srPinned = new LinkedHashMap<>();
    Map<TrafficGraphEdge, List<String>> srTerms = new LinkedHashMap<>();
    accumulateSrAllUp(graph, srPolicies, srPinned, srTerms);

    List<TrafficGraphEdge> edges = sortedRealEdges(graph.getEdges());
    StringBuilder out = new StringBuilder();
    out.append("; Traffic SMT encoding (parallel to reachability smt_encoding.smt2)\n");
    out.append("; Scenario: AllUp. YU Algorithm 1 output is unchanged; this file is separate.\n");
    out.append("; SpecLens: comment (= Config_*_weight <pin>) to unpin SR candidate weights.\n\n");

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
      double yuAllUp = yuLoads.get(edge).evaluateAllUp();
      double pinnedSr = srPinned.getOrDefault(edge, 0.0);
      double ipConst = yuAllUp - pinnedSr;
      if (Math.abs(ipConst) < 1e-9) {
        ipConst = 0.0;
      }
      List<String> terms = srTerms.getOrDefault(edge, java.util.Collections.emptyList());
      String loadExpr = combineLoad(ipConst, terms);
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

  private static Map<String, Integer> collectWeightPins(Map<String, List<SrPolicy>> srPolicies) {
    Map<String, Integer> pins = new TreeMap<>();
    for (List<SrPolicy> policies : srPolicies.values()) {
      for (SrPolicy policy : policies) {
        for (SrPolicy.Path path : policy.getPaths()) {
          String var = path.getWeightConfigVar();
          if (var == null || var.isEmpty()) {
            var =
                GuardedTrafficForwarding.weightConfigVar(
                    policy.getRouter(), policy.getName(), path.getId());
          }
          Integer previous = pins.put(var, path.getWeight());
          if (previous != null && previous != path.getWeight()) {
            throw new IllegalStateException("conflicting pin for " + var);
          }
        }
      }
    }
    return pins;
  }

  private static void accumulateSrAllUp(
      TrafficGraph graph,
      Map<String, List<SrPolicy>> srPolicies,
      Map<TrafficGraphEdge, Double> srPinned,
      Map<TrafficGraphEdge, List<String>> srTerms) {
    for (TrafficFlow flow : graph.getFlows()) {
      if (flow.getForwarding() != TrafficFlow.ForwardingType.SR_POLICY) {
        continue;
      }
      SrPolicy policy = matchingPolicy(srPolicies.get(flow.getSource()), flow);
      if (policy == null) {
        continue;
      }
      List<SrPolicy.Path> paths = policy.getPaths();
      int totalWeight = 0;
      for (SrPolicy.Path path : paths) {
        totalWeight += path.getWeight();
      }
      if (totalWeight <= 0) {
        continue;
      }
      StringBuilder sumWeights = new StringBuilder("(+");
      List<String> configVars = new ArrayList<>();
      for (SrPolicy.Path path : paths) {
        String var = configVar(policy, path);
        configVars.add(var);
        sumWeights.append(" (to_real ").append(var).append(')');
      }
      sumWeights.append(')');
      String denom = paths.size() == 1 ? "(to_real " + configVars.get(0) + ')' : sumWeights.toString();

      double demand = flow.getDemandGbps();
      for (int i = 0; i < paths.size(); i++) {
        SrPolicy.Path path = paths.get(i);
        String var = configVars.get(i);
        double pinnedShare = path.getWeight() / (double) totalWeight;
        // Domain w_i >= 1 ⇒ Σw >= 1; no need for (= Σ 0) ite (that produced dead w=-pin branches).
        String share = "(/ (to_real " + var + ") " + denom + ")";
        String term = "(* " + formatReal(demand) + ' ' + share + ')';
        for (TrafficGraphEdge edge : allUpPathEdges(graph, path)) {
          srPinned.put(edge, srPinned.getOrDefault(edge, 0.0) + demand * pinnedShare);
          srTerms.computeIfAbsent(edge, unused -> new ArrayList<>()).add(term);
        }
      }
    }
  }

  @Nullable
  private static SrPolicy matchingPolicy(@Nullable List<SrPolicy> policies, TrafficFlow flow) {
    if (policies == null) {
      return null;
    }
    SrPolicy best = null;
    int bestSpecificity = -1;
    for (SrPolicy policy : policies) {
      // matchNextHop is null for policies built by GuardedTrafficForwarding.
      if (!policy.matches(flow.getSource(), flow, flow.getDestination().getStartIp())) {
        continue;
      }
      int specificity = policy.matchSpecificity();
      if (specificity > bestSpecificity) {
        best = policy;
        bestSpecificity = specificity;
      }
    }
    return best;
  }

  private static String configVar(SrPolicy policy, SrPolicy.Path path) {
    String var = path.getWeightConfigVar();
    if (var != null && !var.isEmpty()) {
      return var;
    }
    return GuardedTrafficForwarding.weightConfigVar(
        policy.getRouter(), policy.getName(), path.getId());
  }

  private static List<TrafficGraphEdge> allUpPathEdges(TrafficGraph graph, SrPolicy.Path path) {
    List<TrafficGraphEdge> edges = new ArrayList<>();
    for (SrPolicy.Segment segment : path.getSegments()) {
      if (!segment.isAdjacency()) {
        // Node-SID hops need IGP; AllUp SMT v1 only places Adj-SID edges.
        continue;
      }
      TrafficGraphEdge edge = outgoing(graph, segment.getRouter(), segment.getPeer());
      if (edge != null) {
        edges.add(edge);
      }
    }
    return edges;
  }

  @Nullable
  private static TrafficGraphEdge outgoing(TrafficGraph graph, String router, String peer) {
    for (TrafficGraphEdge edge : graph.getOutgoingEdges(router)) {
      if (peer.equals(edge.getPeer())) {
        return edge;
      }
    }
    return null;
  }

  private static String combineLoad(double ipConst, List<String> srTerms) {
    List<String> parts = new ArrayList<>();
    if (Math.abs(ipConst) > 1e-9) {
      parts.add(formatReal(ipConst));
    }
    parts.addAll(srTerms);
    if (parts.isEmpty()) {
      return "0.0";
    }
    if (parts.size() == 1) {
      return parts.get(0);
    }
    StringBuilder out = new StringBuilder("(+");
    for (String part : parts) {
      out.append(' ').append(part);
    }
    return out.append(')').toString();
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
