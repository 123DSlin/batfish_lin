package org.batfish.minesweeper.symbolicroute;

import java.util.Optional;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Protocol adapter for applying an egress policy before advertising a route to one peer. */
@FunctionalInterface
public interface SymbolicRouteEgressPolicy<R extends AbstractRouteDecorator> {

  /** Returns the accepted (possibly transformed) route, or empty when export is denied. */
  Optional<R> process(String sender, String receiver, R route);
}
