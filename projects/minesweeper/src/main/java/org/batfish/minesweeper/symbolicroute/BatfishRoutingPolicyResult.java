package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Optional;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;

/** Result of evaluating one concrete route with Batfish's routing-policy interpreter. */
public final class BatfishRoutingPolicyResult<R extends AbstractRoute> {

  public enum Outcome {
    ACCEPTED,
    DENIED,
    POLICY_NOT_FOUND
  }

  @Nonnull private final Outcome _outcome;
  @Nullable private final AnnotatedRoute<R> _outputRoute;

  private BatfishRoutingPolicyResult(Outcome outcome, @Nullable AnnotatedRoute<R> outputRoute) {
    _outcome = requireNonNull(outcome, "outcome must be provided");
    _outputRoute = outputRoute;
  }

  @Nonnull
  public static <R extends AbstractRoute> BatfishRoutingPolicyResult<R> accepted(
      AnnotatedRoute<R> outputRoute) {
    return new BatfishRoutingPolicyResult<>(
        Outcome.ACCEPTED, requireNonNull(outputRoute, "outputRoute must be provided"));
  }

  @Nonnull
  public static <R extends AbstractRoute> BatfishRoutingPolicyResult<R> denied() {
    return new BatfishRoutingPolicyResult<>(Outcome.DENIED, null);
  }

  @Nonnull
  public static <R extends AbstractRoute> BatfishRoutingPolicyResult<R> policyNotFound() {
    return new BatfishRoutingPolicyResult<>(Outcome.POLICY_NOT_FOUND, null);
  }

  @Nonnull
  public Outcome getOutcome() {
    return _outcome;
  }

  @Nonnull
  public Optional<AnnotatedRoute<R>> getOutputRoute() {
    return Optional.ofNullable(_outputRoute);
  }
}
