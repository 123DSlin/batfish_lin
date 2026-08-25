package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Accepted ingress contribution, its destination candidate key, and resulting RIB delta. */
public final class SymbolicRouteIngressResult<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRouteKey _key;
  @Nonnull private final GuardedRibDelta<R> _delta;

  SymbolicRouteIngressResult(SymbolicRouteKey key, GuardedRibDelta<R> delta) {
    _key = requireNonNull(key, "key must be provided");
    _delta = requireNonNull(delta, "delta must be provided");
  }

  @Nonnull
  public SymbolicRouteKey getKey() {
    return _key;
  }

  @Nonnull
  public GuardedRibDelta<R> getDelta() {
    return _delta;
  }
}
