package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * YU matrix {@code M[l, S]}: symbolic traffic fraction of one flow on edge {@code l} with label
 * stack {@code S}.
 *
 * <p>Missing cells are {@code 0}. Algorithm 1 zeros a fresh matrix each iteration and adds {@code
 * forward} results into it.
 */
public class SymbolicTrafficMatrix {

  private final Map<TrafficGraphEdge, Map<TrafficLabelStack, SymbolicTrafficFraction>> _values;

  public SymbolicTrafficMatrix() {
    _values = new HashMap<>();
  }

  public SymbolicTrafficFraction get(TrafficGraphEdge edge, TrafficLabelStack stack) {
    Map<TrafficLabelStack, SymbolicTrafficFraction> columns = _values.get(edge);
    if (columns == null) {
      return SymbolicTrafficFraction.zero();
    }
    SymbolicTrafficFraction value = columns.get(stack);
    if (value == null) {
      return SymbolicTrafficFraction.zero();
    }
    return value;
  }

  public void put(
      TrafficGraphEdge edge, TrafficLabelStack stack, SymbolicTrafficFraction value) {
    if (value.isZero()) {
      Map<TrafficLabelStack, SymbolicTrafficFraction> columns = _values.get(edge);
      if (columns != null) {
        columns.remove(stack);
        if (columns.isEmpty()) {
          _values.remove(edge);
        }
      }
      return;
    }
    Map<TrafficLabelStack, SymbolicTrafficFraction> columns = _values.get(edge);
    if (columns == null) {
      columns = new HashMap<>();
      _values.put(edge, columns);
    }
    columns.put(stack, value);
  }

  /** {@code this ← this + other}, the {@code M_i ← M_i + forward(...)} step. */
  public void add(SymbolicTrafficMatrix other) {
    addInternal(other, false);
  }

  /**
   * Same as {@link #add} but skips pseudo ingress cells. Accumulated STF for {@code τ_l} must not
   * include {@code l_R}.
   */
  public void addRealLinks(SymbolicTrafficMatrix other) {
    addInternal(other, true);
  }

  private void addInternal(SymbolicTrafficMatrix other, boolean skipPseudoIncoming) {
    for (Map.Entry<TrafficGraphEdge, Map<TrafficLabelStack, SymbolicTrafficFraction>> edgeEntry :
        other._values.entrySet()) {
      TrafficGraphEdge edge = edgeEntry.getKey();
      if (skipPseudoIncoming && edge.isPseudoIncoming()) {
        continue;
      }
      for (Map.Entry<TrafficLabelStack, SymbolicTrafficFraction> stackEntry :
          edgeEntry.getValue().entrySet()) {
        TrafficLabelStack stack = stackEntry.getKey();
        put(edge, stack, get(edge, stack).plus(stackEntry.getValue()));
      }
    }
  }

  public boolean isZero() {
    return _values.isEmpty();
  }

  /** Label stacks that currently have a non-zero cell, used as {@code S} in the next iteration. */
  public Set<TrafficLabelStack> stacks() {
    Set<TrafficLabelStack> stacks = new LinkedHashSet<>();
    for (Map<TrafficLabelStack, SymbolicTrafficFraction> columns : _values.values()) {
      stacks.addAll(columns.keySet());
    }
    return stacks;
  }

  public Set<TrafficGraphEdge> edges() {
    return Collections.unmodifiableSet(_values.keySet());
  }
}
