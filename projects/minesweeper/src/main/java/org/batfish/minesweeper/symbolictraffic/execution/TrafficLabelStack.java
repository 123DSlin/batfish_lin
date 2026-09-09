package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

/**
 * SR label stack {@code S} used as a column of {@code M[l, S]}.
 *
 * <p>The empty stack is YU's {@code ∅} and selects IP forwarding. Non-empty stacks are ordered
 * typed SIDs ({@link SrPolicy.Segment}): Node-SID or Adj-SID. Storing only router names would make
 * every later Adj-SID look like a Node-SID.
 */
public class TrafficLabelStack {

  private final List<SrPolicy.Segment> _segments;

  public static TrafficLabelStack empty() {
    return new TrafficLabelStack(Collections.emptyList());
  }

  public static TrafficLabelStack nodes(String... routers) {
    List<SrPolicy.Segment> segments = new ArrayList<>();
    for (String router : routers) {
      segments.add(SrPolicy.Segment.node(router));
    }
    return new TrafficLabelStack(segments);
  }

  public TrafficLabelStack(List<SrPolicy.Segment> segments) {
    _segments = new ArrayList<>();
    for (SrPolicy.Segment segment : segments) {
      if (segment == null) {
        throw new IllegalArgumentException("label stack segment cannot be null");
      }
      _segments.add(segment);
    }
  }

  public List<SrPolicy.Segment> getSegments() {
    return Collections.unmodifiableList(_segments);
  }

  public SrPolicy.Segment getFirst() {
    return _segments.get(0);
  }

  public TrafficLabelStack pop() {
    return new TrafficLabelStack(_segments.subList(1, _segments.size()));
  }

  public boolean isEmpty() {
    return _segments.isEmpty();
  }

  @Override
  public boolean equals(Object o) {
    if (!(o instanceof TrafficLabelStack)) {
      return false;
    }
    return _segments.equals(((TrafficLabelStack) o)._segments);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_segments);
  }

  @Override
  public String toString() {
    return _segments.toString();
  }
}
