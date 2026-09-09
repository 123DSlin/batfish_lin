package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Per-link symbolic traffic load {@code τ_l = Σ_{f,S} V_f · M_f[l, S]}.
 *
 * <p>{@code M_f} is hop-accumulated STF from {@link SymbolicTrafficExecution#simulate}, not listing
 * {@code M_I}.
 */
public class SymbolicTrafficLoad {

  private final Map<TrafficGraphEdge, SymbolicTrafficFraction> _loads;

  public SymbolicTrafficLoad() {
    _loads = new LinkedHashMap<>();
  }

  public SymbolicTrafficFraction get(TrafficGraphEdge edge) {
    SymbolicTrafficFraction value = _loads.get(edge);
    return value == null ? SymbolicTrafficFraction.zero() : value;
  }

  public void add(TrafficGraphEdge edge, SymbolicTrafficFraction increment) {
    if (edge == null || edge.isPseudoIncoming() || increment == null || increment.isZero()) {
      return;
    }
    SymbolicTrafficFraction next = get(edge).plus(increment);
    if (next.isZero()) {
      _loads.remove(edge);
    } else {
      _loads.put(edge, next);
    }
  }

  public Map<TrafficGraphEdge, SymbolicTrafficFraction> getLoads() {
    return Collections.unmodifiableMap(_loads);
  }
}
