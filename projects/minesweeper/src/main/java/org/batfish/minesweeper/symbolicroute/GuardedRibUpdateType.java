package org.batfish.minesweeper.symbolicroute;

/** Kinds of changes exposed by a guarded RIB operation. */
public enum GuardedRibUpdateType {
  ADDED,
  REMOVED,
  GUARDS_CHANGED
}
