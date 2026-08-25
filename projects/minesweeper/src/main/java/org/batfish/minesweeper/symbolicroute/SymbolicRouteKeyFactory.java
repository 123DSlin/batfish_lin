package org.batfish.minesweeper.symbolicroute;

import org.batfish.datamodel.AbstractRouteDecorator;

/** Protocol adapter for constructing a stable candidate key after ingress policy processing. */
@FunctionalInterface
public interface SymbolicRouteKeyFactory<R extends AbstractRouteDecorator> {

  SymbolicRouteKey create(String receiver, R route);
}
