package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nullable;

/** One semantic change between two stable guarded SID snapshots. */
public final class GuardedSidUpdate {
  public enum Type {
    ADDED,
    REMOVED,
    GUARD_CHANGED,
    REPLACED
  }

  private final Type _type;
  @Nullable private final GuardedSidEntry _oldEntry;
  @Nullable private final GuardedSidEntry _newEntry;

  static GuardedSidUpdate added(GuardedSidEntry entry) {
    return new GuardedSidUpdate(Type.ADDED, null, requireNonNull(entry));
  }

  static GuardedSidUpdate removed(GuardedSidEntry entry) {
    return new GuardedSidUpdate(Type.REMOVED, requireNonNull(entry), null);
  }

  static GuardedSidUpdate changed(GuardedSidEntry oldEntry, GuardedSidEntry newEntry) {
    Type type =
        oldEntry.getBinding().equals(newEntry.getBinding()) ? Type.GUARD_CHANGED : Type.REPLACED;
    return new GuardedSidUpdate(type, requireNonNull(oldEntry), requireNonNull(newEntry));
  }

  private GuardedSidUpdate(
      Type type, @Nullable GuardedSidEntry oldEntry, @Nullable GuardedSidEntry newEntry) {
    _type = requireNonNull(type);
    _oldEntry = oldEntry;
    _newEntry = newEntry;
  }

  public Type getType() {
    return _type;
  }

  @Nullable
  public GuardedSidEntry getOldEntry() {
    return _oldEntry;
  }

  @Nullable
  public GuardedSidEntry getNewEntry() {
    return _newEntry;
  }
}
