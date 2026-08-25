package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayDeque;
import java.util.Queue;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Deterministic FIFO work queue for guarded route advertisements. */
public final class SymbolicRouteWorkQueue<R extends AbstractRouteDecorator> {

  private final Queue<SymbolicRouteMessage<R>> _queue;

  public SymbolicRouteWorkQueue() {
    _queue = new ArrayDeque<>();
  }

  public void enqueue(SymbolicRouteMessage<R> message) {
    _queue.add(requireNonNull(message, "message must be provided"));
  }

  @Nullable
  public SymbolicRouteMessage<R> poll() {
    return _queue.poll();
  }

  public boolean isEmpty() {
    return _queue.isEmpty();
  }

  public int size() {
    return _queue.size();
  }
}
