package org.batfish.minesweeper.symbolicroute;

import org.batfish.datamodel.AbstractRouteDecorator;

/** Protocol adapter for assigning a stable identity to an exported advertisement. */
@FunctionalInterface
public interface SymbolicRouteMessageIdFactory<R extends AbstractRouteDecorator> {

  String create(String sender, String receiver, R route);
}
