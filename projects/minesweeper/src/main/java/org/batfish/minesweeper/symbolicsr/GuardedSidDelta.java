package org.batfish.minesweeper.symbolicsr;

import com.google.common.collect.ImmutableList;

/** Ordered semantic changes emitted by one SID database reconciliation. */
public final class GuardedSidDelta {
  private final ImmutableList<GuardedSidUpdate> _updates;

  GuardedSidDelta(Iterable<GuardedSidUpdate> updates) {
    _updates = ImmutableList.copyOf(updates);
  }

  public ImmutableList<GuardedSidUpdate> getUpdates() {
    return _updates;
  }

  public boolean isEmpty() {
    return _updates.isEmpty();
  }
}
