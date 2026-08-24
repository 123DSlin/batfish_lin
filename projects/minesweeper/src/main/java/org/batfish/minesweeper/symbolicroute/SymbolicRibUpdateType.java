package org.batfish.minesweeper.symbolicroute;

/** Kinds of changes to a guarded candidate RIB. */
public enum SymbolicRibUpdateType {
  ADDED,
  REMOVED,
  AVAILABILITY_GUARD_CHANGED
}
