package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.batfish.datamodel.Ip;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * YU encoding of route iteration: {@code VIGP_nip[l]} and {@code VSR_p[l]}.
 *
 * <p>{@code VIGP_nip[l] = Σ_{r : nh_r = l} c^{nip}_r}. {@code c_p = (g_p w_p) / Σ_{p'} (g_{p'}
 * w_{p'})} and {@code VSR_p[l] = c_p · VIGP_ip[l]} where {@code ip} is the first node of {@code p}.
 */
public final class RouteIterationEncoding {

  private RouteIterationEncoding() {}

  public static Map<TrafficGraphEdge, SymbolicTrafficFraction> vigp(
      List<ForwardingRule> rib, Ip nextHopIp) {
    Map<TrafficGraphEdge, SymbolicTrafficFraction> vector = new LinkedHashMap<>();
    for (ForwardingRule rule : rib) {
      TrafficGraphEdge link = rule.getDirectNextHop();
      if (link == null) {
        continue;
      }
      SymbolicTrafficFraction share = RouteSelectionEncoding.ecmpRatio(rule, rib, nextHopIp);
      SymbolicTrafficFraction previous = vector.get(link);
      vector.put(link, previous == null ? share : previous.plus(share));
    }
    return vector;
  }

  public static SymbolicTrafficFraction pathShare(SrPolicy.Path path, List<SrPolicy.Path> paths) {
    SymbolicTrafficFraction numerator =
        SymbolicTrafficFraction.fromGuard(path.getGuard()).times(path.getWeight());
    SymbolicTrafficFraction denominator = SymbolicTrafficFraction.zero();
    for (SrPolicy.Path other : paths) {
      denominator =
          denominator.plus(
              SymbolicTrafficFraction.fromGuard(other.getGuard()).times(other.getWeight()));
    }
    return numerator.div(denominator);
  }

  public static Map<TrafficGraphEdge, SymbolicTrafficFraction> vsr(
      SrPolicy.Path path, List<SrPolicy.Path> paths, List<ForwardingRule> igpRib, Ip firstNodeIp) {
    SymbolicTrafficFraction pathRatio = pathShare(path, paths);
    Map<TrafficGraphEdge, SymbolicTrafficFraction> vector = new LinkedHashMap<>();
    for (Map.Entry<TrafficGraphEdge, SymbolicTrafficFraction> igp :
        vigp(igpRib, firstNodeIp).entrySet()) {
      vector.put(igp.getKey(), pathRatio.times(igp.getValue()));
    }
    return vector;
  }
}
