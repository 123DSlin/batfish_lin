package org.batfish.minesweeper.smt;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Expr;
import com.microsoft.z3.Solver;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nullable;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrPolicy;
import org.batfish.datamodel.sr.SrPolicyEndpoint;
import org.batfish.datamodel.sr.SrSegment;
import org.batfish.datamodel.sr.SrSegmentList;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.GraphEdge;

/** Encodes parsed SR policies and exposes their forwarding contribution to the main SMT slice. */
final class SrPolicySmtEncoder {

  static final class SliceEncoding {
    private final Map<String, Map<GraphEdge, List<BoolExpr>>> _forwarding = new LinkedHashMap<>();
    private final Map<String, List<BoolExpr>> _active = new LinkedHashMap<>();

    private void add(String router, GraphEdge edge, BoolExpr selectedForwarding) {
      _forwarding
          .computeIfAbsent(router, unused -> new LinkedHashMap<>())
          .computeIfAbsent(edge, unused -> new ArrayList<>())
          .add(selectedForwarding);
    }

    private void addActive(String router, BoolExpr selected) {
      _active.computeIfAbsent(router, unused -> new ArrayList<>()).add(selected);
    }

    BoolExpr active(EncoderSlice slice, String router) {
      return or(slice, _active.getOrDefault(router, List.of()));
    }

    BoolExpr forwarding(EncoderSlice slice, String router, GraphEdge edge) {
      return or(slice, _forwarding.getOrDefault(router, Map.of()).getOrDefault(edge, List.of()));
    }
  }

  private static final class ResolvedSegment {
    private final SrSidBindingKey _key;

    private ResolvedSegment(SrSidBindingKey key) {
      _key = key;
    }
  }

  private SrPolicySmtEncoder() {}

  static void initConfigurationConstants(
      Context ctx,
      Solver solver,
      Map<String, Expr> allVariables,
      Map<String, Configuration> configurations) {
    for (Configuration configuration : configurations.values()) {
      SegmentRoutingConfig sr = configuration.getSegmentRoutingConfig();
      if (sr == null) {
        continue;
      }
      for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
        for (SrPolicy policy : vrf.getPolicies()) {
          for (SrCandidatePath candidate : policy.getCandidates()) {
            String name = weightVariable(configuration.getHostname(), policy, candidate);
            ArithExpr variable = ctx.mkIntConst(name);
            allVariables.put(variable.toString(), variable);
            solver.add(ctx.mkEq(variable, ctx.mkInt(candidate.getWeight())));
            solver.add(ctx.mkGe(variable, ctx.mkInt(1)));
            solver.add(ctx.mkLe(variable, ctx.mkInt(SrCandidatePath.MAX_UNSIGNED_INT)));
          }
        }
      }
    }
  }

  static SliceEncoding encode(EncoderSlice slice, IsisSpfSmtEncoder.SliceEncoding isis) {
    SliceEncoding result = new SliceEncoding();
    Map<Long, List<SrSidBinding>> labels = labelBindings(slice.getGraph().getConfigurations());
    for (Configuration configuration : slice.getGraph().getConfigurations().values()) {
      SegmentRoutingConfig sr = configuration.getSegmentRoutingConfig();
      if (sr == null) {
        continue;
      }
      for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
        Map<String, SrSegmentList> lists = new HashMap<>();
        vrf.getSegmentLists().forEach(list -> lists.put(list.getKey().getName(), list));
        for (SrPolicy policy : vrf.getPolicies()) {
          encodePolicy(slice, isis, labels, configuration, policy, lists, result);
        }
      }
    }
    return result;
  }

  private static void encodePolicy(
      EncoderSlice slice,
      IsisSpfSmtEncoder.SliceEncoding isis,
      Map<Long, List<SrSidBinding>> labels,
      Configuration owner,
      SrPolicy policy,
      Map<String, SrSegmentList> lists,
      SliceEncoding result) {
    List<SrCandidatePath> candidates = new ArrayList<>(policy.getCandidates());
    candidates.sort(
        Comparator.comparingLong(SrCandidatePath::getPreference)
            .reversed()
            .thenComparing(SrCandidatePath::getName));
    Map<SrCandidatePath, BoolExpr> available = new LinkedHashMap<>();
    Map<SrCandidatePath, Map<String, Map<GraphEdge, List<BoolExpr>>>> forwarding =
        new LinkedHashMap<>();
    for (SrCandidatePath candidate : candidates) {
      Map<String, Map<GraphEdge, List<BoolExpr>>> candidateForwarding = new LinkedHashMap<>();
      forwarding.put(candidate, candidateForwarding);
      SrSegmentList list = lists.get(candidate.getSegmentList());
      BoolExpr expression =
          list == null
              ? slice.mkFalse()
              : segmentListAvailable(
                  slice,
                  isis,
                  labels,
                  owner.getHostname(),
                  policy,
                  candidate,
                  list,
                  candidateForwarding);
      String stem = candidateStem(owner.getHostname(), policy, candidate);
      BoolExpr variable = slice.getCtx().mkBoolConst(stem + "_available");
      register(slice, variable);
      slice.add(slice.mkEq(variable, slice.mkAnd(endpointMatches(slice, policy), expression)));
      available.put(candidate, variable);
    }

    for (SrCandidatePath candidate : candidates) {
      List<BoolExpr> higher = new ArrayList<>();
      for (SrCandidatePath other : candidates) {
        if (other.getPreference() > candidate.getPreference()) {
          higher.add(available.get(other));
        }
      }
      BoolExpr selected =
          slice
              .getCtx()
              .mkBoolConst(candidateStem(owner.getHostname(), policy, candidate) + "_selected");
      register(slice, selected);
      slice.add(
          slice.mkEq(
              selected, slice.mkAnd(available.get(candidate), slice.mkNot(or(slice, higher)))));
      forwarding
          .get(candidate)
          .forEach(
              (router, byEdge) -> {
                result.addActive(router, selected);
                byEdge.forEach(
                    (edge, expressions) ->
                        expressions.forEach(
                            expression ->
                                result.add(router, edge, slice.mkAnd(selected, expression))));
              });
    }
  }

  private static BoolExpr segmentListAvailable(
      EncoderSlice slice,
      IsisSpfSmtEncoder.SliceEncoding isis,
      Map<Long, List<SrSidBinding>> labels,
      String ingress,
      SrPolicy policy,
      SrCandidatePath candidate,
      SrSegmentList list,
      Map<String, Map<GraphEdge, List<BoolExpr>>> forwarding) {
    String current = ingress;
    List<BoolExpr> requirements = new ArrayList<>();
    int index = 0;
    for (SrSegment segment : list.getSegments()) {
      ResolvedSegment resolved = resolve(segment, labels, current);
      if (resolved == null) {
        return slice.mkFalse();
      }
      SrSidBindingKey key = resolved._key;
      String segmentStem = candidateStem(ingress, policy, candidate) + "_segment_" + index;
      switch (key.getType()) {
        case ADJACENCY:
          GraphEdge adjacency = outgoing(slice, key.getNode(), key.getInterfaceName());
          if (adjacency == null || adjacency.getPeer() == null || !current.equals(key.getNode())) {
            return slice.mkFalse();
          }
          BoolExpr adjacencyUp = IsisSpfSmtEncoder.edgeUp(slice, adjacency);
          requirements.add(adjacencyUp);
          emitForwarding(slice, segmentStem, Map.of(adjacency, adjacencyUp), forwarding);
          current = adjacency.getPeer();
          break;
        case NODE:
        case PREFIX:
          if (key.getPrefix() == null || key.getPrefix().getIpv4() == null) {
            return slice.mkFalse();
          }
          Prefix prefix = key.getPrefix().getIpv4();
          BoolExpr routeAvailable = isis.routeAvailable(slice, current, prefix);
          requirements.add(routeAvailable);
          emitForwarding(
              slice, segmentStem, isis.nextHopsToPrefix(slice, current, prefix), forwarding);
          current = key.getNode();
          break;
        case BINDING:
        default:
          // Recursive binding-policy expansion is intentionally rejected until cycle detection and
          // preference inheritance are encoded.
          return slice.mkFalse();
      }
      index++;
    }
    return and(slice, requirements);
  }

  private static void emitForwarding(
      EncoderSlice slice,
      String stem,
      Map<GraphEdge, BoolExpr> forwarding,
      Map<String, Map<GraphEdge, List<BoolExpr>>> result) {
    for (Map.Entry<GraphEdge, BoolExpr> entry : forwarding.entrySet()) {
      BoolExpr variable =
          slice
              .getCtx()
              .mkBoolConst(
                  stem
                      + "_forward_"
                      + sanitize(entry.getKey().getRouter())
                      + "_"
                      + sanitize(entry.getKey().getStart().getName()));
      register(slice, variable);
      slice.add(slice.mkEq(variable, entry.getValue()));
      result
          .computeIfAbsent(entry.getKey().getRouter(), unused -> new LinkedHashMap<>())
          .computeIfAbsent(entry.getKey(), unused -> new ArrayList<>())
          .add(variable);
    }
  }

  @Nullable
  private static ResolvedSegment resolve(
      SrSegment segment, Map<Long, List<SrSidBinding>> labels, String currentNode) {
    if (segment.getBindingKey() != null) {
      return new ResolvedSegment(segment.getBindingKey());
    }
    SrSidValue sid = segment.getSid();
    if (sid == null || sid.getType() != SrSidValue.Type.MPLS_LABEL) {
      return null;
    }
    List<SrSidBinding> bindings = labels.get(sid.getMplsLabel());
    if (bindings == null) {
      return null;
    }
    // Adjacency SIDs have local significance. Prefer the binding owned by the router currently
    // processing the label. A globally unique node/prefix label remains usable from any router.
    List<SrSidBinding> local = new ArrayList<>();
    for (SrSidBinding binding : bindings) {
      if (binding.getKey().getNode().equals(currentNode)) {
        local.add(binding);
      }
    }
    List<SrSidBinding> candidates = local.isEmpty() ? bindings : local;
    return candidates.size() == 1 ? new ResolvedSegment(candidates.get(0).getKey()) : null;
  }

  private static Map<Long, List<SrSidBinding>> labelBindings(
      Map<String, Configuration> configurations) {
    Map<Long, List<SrSidBinding>> result = new LinkedHashMap<>();
    for (Configuration configuration : configurations.values()) {
      SegmentRoutingConfig sr = configuration.getSegmentRoutingConfig();
      if (sr == null) {
        continue;
      }
      for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
        for (SrSidBinding binding : vrf.getSidBindings()) {
          if (binding.getSid().getType() == SrSidValue.Type.MPLS_LABEL) {
            result
                .computeIfAbsent(binding.getSid().getMplsLabel(), unused -> new ArrayList<>())
                .add(binding);
          }
        }
      }
    }
    return result;
  }

  private static BoolExpr endpointMatches(EncoderSlice slice, SrPolicy policy) {
    SrPolicyEndpoint endpoint = policy.getKey().getEndpoint();
    if (endpoint.getFamily() != SrPolicyEndpoint.Family.IPV4 || endpoint.getIpv4() == null) {
      return slice.mkFalse();
    }
    return slice.isRelevantFor(
        Prefix.create(endpoint.getIpv4(), Prefix.MAX_PREFIX_LENGTH),
        slice.getSymbolicPacket().getDstIp());
  }

  @Nullable
  private static GraphEdge outgoing(EncoderSlice slice, String router, String iface) {
    for (GraphEdge edge : slice.getGraph().getEdgeMap().getOrDefault(router, List.of())) {
      if (edge.getStart().getName().equals(iface)) {
        return edge;
      }
    }
    return null;
  }

  static String weightVariable(String hostname, SrPolicy policy, SrCandidatePath candidate) {
    return "Config_"
        + sanitize(hostname)
        + "_SrPolicy_"
        + sanitize(policy.getName())
        + "_Path_"
        + sanitize(candidate.getName())
        + "_weight";
  }

  private static String candidateStem(String hostname, SrPolicy policy, SrCandidatePath candidate) {
    return "SR-POLICY_"
        + sanitize(hostname)
        + "_"
        + sanitize(policy.getName())
        + "_"
        + sanitize(candidate.getName());
  }

  private static BoolExpr or(EncoderSlice slice, List<BoolExpr> expressions) {
    return expressions.isEmpty()
        ? slice.mkFalse()
        : slice.mkOr(expressions.toArray(new BoolExpr[0]));
  }

  private static BoolExpr and(EncoderSlice slice, List<BoolExpr> expressions) {
    return expressions.isEmpty()
        ? slice.mkTrue()
        : slice.mkAnd(expressions.toArray(new BoolExpr[0]));
  }

  private static void register(EncoderSlice slice, Expr expression) {
    slice.getAllVariables().put(expression.toString(), expression);
  }

  private static String sanitize(String raw) {
    return raw.replaceAll("[^A-Za-z0-9_]", "_");
  }
}
