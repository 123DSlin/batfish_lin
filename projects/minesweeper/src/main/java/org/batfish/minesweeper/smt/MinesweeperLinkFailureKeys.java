package org.batfish.minesweeper.smt;

import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.minesweeper.GraphEdge;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;

/** Canonical identity adapter between Minesweeper forwarding edges and symbolic-route links. */
public final class MinesweeperLinkFailureKeys {

  private MinesweeperLinkFailureKeys() {}

  /** Returns empty for external/null-peer and abstract edges, which lack an internal-link key. */
  @Nonnull
  public static Optional<LinkFailureKey> fromGraphEdge(GraphEdge edge) {
    if (edge.getPeer() == null || edge.isAbstract()) {
      return Optional.empty();
    }
    return Optional.of(LinkFailureKey.of(edge.getRouter(), edge.getPeer()));
  }
}
