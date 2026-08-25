package org.batfish.minesweeper.symbolicroute;

import java.util.Comparator;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Protocol-specific route semantics consumed by the protocol-neutral symbolic route engine. */
public interface SymbolicRouteProtocolAdapter<R extends AbstractRouteDecorator> {

  /** Returns the route preference order used by the receiver's guarded RIB. */
  @Nonnull
  Comparator<R> preferenceComparator(String receiver);

  /** Applies the receiver's import policy. Empty means that the advertisement is denied. */
  @Nonnull
  Optional<R> processImport(SymbolicRouteMessage<R> message);

  /** Constructs the candidate identity after import-policy transformation. */
  @Nonnull
  SymbolicRouteKey createCandidateKey(String receiver, R importedRoute);

  /** Applies export policy on one directed protocol session. Empty means deny. */
  @Nonnull
  Optional<R> processExport(SymbolicRouteSession session, R selectedRoute);

  /** Assigns a stable identity to one exported concrete route on a directed session. */
  @Nonnull
  String createExportMessageId(SymbolicRouteSession session, R exportedRoute);
}
