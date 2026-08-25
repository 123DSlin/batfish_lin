package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** An ingress-policy result prepared for validation before it is installed in a guarded RIB. */
final class SymbolicRouteIngressCandidate<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRouteContributionId _contributionId;
  @Nonnull private final SymbolicRoute<R> _candidate;

  SymbolicRouteIngressCandidate(
      SymbolicRouteContributionId contributionId, SymbolicRoute<R> candidate) {
    _contributionId = requireNonNull(contributionId, "contributionId must be provided");
    _candidate = requireNonNull(candidate, "candidate must be provided");
  }

  @Nonnull
  SymbolicRouteContributionId getContributionId() {
    return _contributionId;
  }

  @Nonnull
  SymbolicRoute<R> getCandidate() {
    return _candidate;
  }
}
