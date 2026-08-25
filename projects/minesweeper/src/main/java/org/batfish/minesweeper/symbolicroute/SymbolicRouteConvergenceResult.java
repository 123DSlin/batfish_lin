package org.batfish.minesweeper.symbolicroute;

/** Summary of a completed symbolic route work-queue convergence run. */
public final class SymbolicRouteConvergenceResult {

  private final int _processedMessages;
  private final int _ribUpdates;

  SymbolicRouteConvergenceResult(int processedMessages, int ribUpdates) {
    _processedMessages = processedMessages;
    _ribUpdates = ribUpdates;
  }

  public int getProcessedMessages() {
    return _processedMessages;
  }

  public int getRibUpdates() {
    return _ribUpdates;
  }
}
