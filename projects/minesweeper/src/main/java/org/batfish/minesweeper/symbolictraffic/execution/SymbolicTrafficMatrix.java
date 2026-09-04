package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.HashMap;
import java.util.Map;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * YU matrix {@code M[l, S]}: symbolic traffic fraction of one flow on edge {@code l} with label
 * stack {@code S}.
 *
 * <p>The formula representation is left unset until Algorithm 1 is implemented. This class only
 * owns the matrix shape.
 */
public class SymbolicTrafficMatrix {

  private final Map<TrafficGraphEdge, Map<TrafficLabelStack, Object>> _values;

  public SymbolicTrafficMatrix() {
    _values = new HashMap<>();
  }

  public Map<TrafficGraphEdge, Map<TrafficLabelStack, Object>> getValues() {
    return _values;
  }
}
