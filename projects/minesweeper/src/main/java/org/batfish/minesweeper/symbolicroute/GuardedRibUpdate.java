package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** One candidate change caused by a guarded RIB operation. */
public final class GuardedRibUpdate<R extends AbstractRouteDecorator> {

  @Nonnull private final GuardedRibUpdateType _type;
  @Nullable private final GuardedRibEntry<R> _oldEntry;
  @Nullable private final GuardedRibEntry<R> _newEntry;

  private GuardedRibUpdate(
      GuardedRibUpdateType type,
      @Nullable GuardedRibEntry<R> oldEntry,
      @Nullable GuardedRibEntry<R> newEntry) {
    _type = requireNonNull(type, "type must be provided");
    _oldEntry = oldEntry;
    _newEntry = newEntry;
  }

  static <R extends AbstractRouteDecorator> GuardedRibUpdate<R> added(GuardedRibEntry<R> entry) {
    return new GuardedRibUpdate<>(GuardedRibUpdateType.ADDED, null, entry);
  }

  static <R extends AbstractRouteDecorator> GuardedRibUpdate<R> removed(GuardedRibEntry<R> entry) {
    return new GuardedRibUpdate<>(GuardedRibUpdateType.REMOVED, entry, null);
  }

  static <R extends AbstractRouteDecorator> GuardedRibUpdate<R> guardsChanged(
      GuardedRibEntry<R> oldEntry, GuardedRibEntry<R> newEntry) {
    return new GuardedRibUpdate<>(GuardedRibUpdateType.GUARDS_CHANGED, oldEntry, newEntry);
  }

  @Nonnull
  public GuardedRibUpdateType getType() {
    return _type;
  }

  @Nullable
  public GuardedRibEntry<R> getOldEntry() {
    return _oldEntry;
  }

  @Nullable
  public GuardedRibEntry<R> getNewEntry() {
    return _newEntry;
  }
}
