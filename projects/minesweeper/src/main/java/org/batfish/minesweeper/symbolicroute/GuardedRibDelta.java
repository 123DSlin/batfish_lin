package org.batfish.minesweeper.symbolicroute;

import com.google.common.collect.ImmutableList;
import java.util.List;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Immutable set of candidate changes caused by one guarded RIB operation. */
public final class GuardedRibDelta<R extends AbstractRouteDecorator> {

  @Nonnull private final List<GuardedRibUpdate<R>> _updates;

  GuardedRibDelta(Iterable<GuardedRibUpdate<R>> updates) {
    _updates = ImmutableList.copyOf(updates);
  }

  @Nonnull
  public List<GuardedRibUpdate<R>> getUpdates() {
    return _updates;
  }

  public boolean isEmpty() {
    return _updates.isEmpty();
  }
}
