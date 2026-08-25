package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Advertisement or withdrawal processed by the network convergence queue. */
final class SymbolicRouteWorkItem<R extends AbstractRouteDecorator> {

  enum Type {
    ADVERTISE,
    WITHDRAW
  }

  @Nonnull private final Type _type;
  @Nullable private final SymbolicRouteMessage<R> _message;
  @Nullable private final SymbolicRouteContributionId _withdrawal;
  @Nullable private final RouteGuard _expectedGuard;

  private SymbolicRouteWorkItem(
      Type type,
      @Nullable SymbolicRouteMessage<R> message,
      @Nullable SymbolicRouteContributionId withdrawal,
      @Nullable RouteGuard expectedGuard) {
    _type = requireNonNull(type, "type must be provided");
    _message = message;
    _withdrawal = withdrawal;
    _expectedGuard = expectedGuard;
  }

  static <R extends AbstractRouteDecorator> SymbolicRouteWorkItem<R> advertise(
      SymbolicRouteMessage<R> message) {
    return new SymbolicRouteWorkItem<>(Type.ADVERTISE, requireNonNull(message), null, null);
  }

  static <R extends AbstractRouteDecorator> SymbolicRouteWorkItem<R> withdraw(
      SymbolicRouteContributionId withdrawal, RouteGuard expectedGuard) {
    return new SymbolicRouteWorkItem<>(
        Type.WITHDRAW, null, requireNonNull(withdrawal), requireNonNull(expectedGuard));
  }

  @Nonnull
  Type getType() {
    return _type;
  }

  @Nonnull
  SymbolicRouteMessage<R> getMessage() {
    if (_message == null) {
      throw new IllegalStateException("withdrawal has no advertisement message");
    }
    return _message;
  }

  @Nonnull
  SymbolicRouteContributionId getWithdrawal() {
    if (_withdrawal == null) {
      throw new IllegalStateException("advertisement has no withdrawal identity");
    }
    return _withdrawal;
  }

  @Nonnull
  RouteGuard getExpectedGuard() {
    if (_expectedGuard == null) {
      throw new IllegalStateException("advertisement has no withdrawal guard");
    }
    return _expectedGuard;
  }
}
