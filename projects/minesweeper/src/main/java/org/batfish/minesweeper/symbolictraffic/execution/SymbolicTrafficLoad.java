package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.HashMap;
import java.util.Map;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * Per-link symbolic traffic load {@code τ_l = Σ_{f,S} V_f · M_f[l, S]}.
 *
 * <p>{@code M_f} is hop-accumulated STF from {@link SymbolicTrafficExecution#simulate}, not listing
 * {@code M_I}. Demand scaling is not implemented yet.
 */
public class SymbolicTrafficLoad {

  private final Map<TrafficGraphEdge, Object> _loads;

  public SymbolicTrafficLoad() {
    _loads = new HashMap<>();
  }

  public Map<TrafficGraphEdge, Object> getLoads() {
    return _loads;
  }
}
