package org.batfish.minesweeper.symbolicroute;

import java.util.Optional;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Protocol adapter for applying a receiver's ingress policy to one route advertisement. */
@FunctionalInterface
public interface SymbolicRouteIngressPolicy<R extends AbstractRouteDecorator> {

  /** Returns the accepted (possibly transformed) route, or empty when the message is denied. */
  Optional<R> process(SymbolicRouteMessage<R> message);
}
