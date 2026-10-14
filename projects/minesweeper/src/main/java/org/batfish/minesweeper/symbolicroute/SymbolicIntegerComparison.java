package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableMap;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;

/** A persisted comparison between two sums of positive integer configuration variables. */
public final class SymbolicIntegerComparison {
  private final ImmutableMap<String, Integer> _left;
  private final ImmutableMap<String, Integer> _right;
  private final ImmutableMap<String, Long> _pins;

  @JsonCreator
  public SymbolicIntegerComparison(
      @JsonProperty("left") Map<String, Integer> left,
      @JsonProperty("right") Map<String, Integer> right,
      @JsonProperty("pins") Map<String, Long> pins) {
    _left = ImmutableMap.copyOf(new TreeMap<>(requireNonNull(left)));
    _right = ImmutableMap.copyOf(new TreeMap<>(requireNonNull(right)));
    _pins = ImmutableMap.copyOf(new TreeMap<>(requireNonNull(pins)));
    if (_left.isEmpty() && _right.isEmpty()) {
      throw new IllegalArgumentException("integer comparison requires at least one term");
    }
    for (String variable : variables()) {
      if (!_pins.containsKey(variable) || _pins.get(variable) <= 0L) {
        throw new IllegalArgumentException("positive pin missing for " + variable);
      }
    }
  }

  @JsonProperty("left")
  public ImmutableMap<String, Integer> getLeft() {
    return _left;
  }

  @JsonProperty("right")
  public ImmutableMap<String, Integer> getRight() {
    return _right;
  }

  @JsonProperty("pins")
  public ImmutableMap<String, Long> getPins() {
    return _pins;
  }

  public java.util.Set<String> variables() {
    java.util.Set<String> result = new java.util.TreeSet<>(_left.keySet());
    result.addAll(_right.keySet());
    return result;
  }

  public long pinnedLeft() {
    return evaluate(_left);
  }

  public long pinnedRight() {
    return evaluate(_right);
  }

  private long evaluate(Map<String, Integer> terms) {
    long result = 0L;
    for (Map.Entry<String, Integer> term : terms.entrySet()) {
      result = Math.addExact(result, Math.multiplyExact(_pins.get(term.getKey()), term.getValue()));
    }
    return result;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) return true;
    if (!(object instanceof SymbolicIntegerComparison)) return false;
    SymbolicIntegerComparison that = (SymbolicIntegerComparison) object;
    return _left.equals(that._left) && _right.equals(that._right) && _pins.equals(that._pins);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_left, _right, _pins);
  }
}
