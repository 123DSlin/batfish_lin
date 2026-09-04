package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * SR label stack {@code S} used as a column of {@code M[l, S]}.
 *
 * <p>The empty stack is YU's {@code ∅} and selects IP forwarding. Non-empty stacks are ordered
 * node identifiers {@code [R1, ..., Rj]}.
 */
public class TrafficLabelStack {

  private final List<String> _labels;

  public static TrafficLabelStack empty() {
    return new TrafficLabelStack(Collections.emptyList());
  }

  public TrafficLabelStack(List<String> labels) {
    _labels = new ArrayList<>(labels);
  }

  public List<String> getLabels() {
    return Collections.unmodifiableList(_labels);
  }

  public boolean isEmpty() {
    return _labels.isEmpty();
  }

  @Override
  public boolean equals(Object o) {
    if (!(o instanceof TrafficLabelStack)) {
      return false;
    }
    return _labels.equals(((TrafficLabelStack) o)._labels);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_labels);
  }

  @Override
  public String toString() {
    return _labels.toString();
  }
}
