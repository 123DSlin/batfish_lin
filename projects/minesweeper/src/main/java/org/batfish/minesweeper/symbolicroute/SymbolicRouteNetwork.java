package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** A fully assembled protocol-neutral symbolic route network and its initial advertisements. */
public final class SymbolicRouteNetwork<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRouteConvergenceEngine<R> _engine;
  @Nonnull private final Map<String, GuardedRib<R>> _ribs;
  @Nonnull private final ImmutableList<SymbolicRouteMessage<R>> _initialAdvertisements;
  @Nonnull private final SymbolicRoutePropagationDependencies _dependencies;

  SymbolicRouteNetwork(
      SymbolicRouteConvergenceEngine<R> engine,
      Map<String, GuardedRib<R>> ribs,
      Iterable<SymbolicRouteMessage<R>> initialAdvertisements,
      SymbolicRoutePropagationDependencies dependencies) {
    _engine = requireNonNull(engine, "engine must be provided");
    _ribs = ImmutableMap.copyOf(requireNonNull(ribs, "ribs must be provided"));
    _initialAdvertisements =
        ImmutableList.copyOf(
            requireNonNull(initialAdvertisements, "initialAdvertisements must be provided"));
    _dependencies = requireNonNull(dependencies, "dependencies must be provided");
  }

  /** Runs the configured initial advertisements to convergence. */
  public SymbolicRouteConvergenceResult converge() {
    return _engine.converge(_initialAdvertisements);
  }

  @Nonnull
  public SymbolicRouteConvergenceEngine<R> getEngine() {
    return _engine;
  }

  @Nonnull
  public Map<String, GuardedRib<R>> getRibs() {
    return _ribs;
  }

  @Nonnull
  public GuardedRib<R> getRib(String router) {
    GuardedRib<R> rib = _ribs.get(requireNonNull(router, "router must be provided"));
    if (rib == null) {
      throw new IllegalArgumentException("no guarded RIB for router");
    }
    return rib;
  }

  @Nonnull
  public SymbolicRoutePropagationDependencies getDependencies() {
    return _dependencies;
  }
}
