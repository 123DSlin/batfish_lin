package org.batfish.minesweeper.symbolicroute;

import com.google.common.collect.ImmutableList;
import java.util.List;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Immutable collection of changes produced by one guarded RIB operation. */
public final class SymbolicRibDelta<R extends AbstractRouteDecorator> {

  @Nonnull private final List<SymbolicRibUpdate<R>> _updates;

  public SymbolicRibDelta(Iterable<SymbolicRibUpdate<R>> updates) {
    _updates = ImmutableList.copyOf(updates);
  }

  @Nonnull
  public List<SymbolicRibUpdate<R>> getUpdates() {
    return _updates;
  }

  public boolean isEmpty() {
    return _updates.isEmpty();
  }
}
