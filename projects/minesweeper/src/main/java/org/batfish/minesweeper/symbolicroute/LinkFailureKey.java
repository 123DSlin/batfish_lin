package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.Preconditions.checkArgument;
import static java.util.Objects.requireNonNull;

import java.util.Objects;
import javax.annotation.Nonnull;

/** Stable, direction-independent identity for one Minesweeper internal-link failure variable. */
public final class LinkFailureKey implements Comparable<LinkFailureKey> {

  @Nonnull private final String _firstRouter;
  @Nonnull private final String _secondRouter;

  public static LinkFailureKey of(String firstRouter, String secondRouter) {
    requireNonNull(firstRouter, "firstRouter must be provided");
    requireNonNull(secondRouter, "secondRouter must be provided");
    checkArgument(!firstRouter.isEmpty(), "firstRouter must not be empty");
    checkArgument(!secondRouter.isEmpty(), "secondRouter must not be empty");
    checkArgument(!firstRouter.equals(secondRouter), "link endpoints must be different routers");
    return firstRouter.compareTo(secondRouter) < 0
        ? new LinkFailureKey(firstRouter, secondRouter)
        : new LinkFailureKey(secondRouter, firstRouter);
  }

  private LinkFailureKey(String firstRouter, String secondRouter) {
    _firstRouter = firstRouter;
    _secondRouter = secondRouter;
  }

  @Nonnull
  public String getFirstRouter() {
    return _firstRouter;
  }

  @Nonnull
  public String getSecondRouter() {
    return _secondRouter;
  }

  public boolean containsRouter(String router) {
    return _firstRouter.equals(router) || _secondRouter.equals(router);
  }

  /** Human-readable guard name; identity comparisons never parse this string. */
  @Nonnull
  public String guardName() {
    return _firstRouter + "_" + _secondRouter;
  }

  @Override
  public int compareTo(LinkFailureKey other) {
    int firstComparison = _firstRouter.compareTo(other._firstRouter);
    return firstComparison != 0 ? firstComparison : _secondRouter.compareTo(other._secondRouter);
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) {
      return true;
    }
    if (!(obj instanceof LinkFailureKey)) {
      return false;
    }
    LinkFailureKey other = (LinkFailureKey) obj;
    return _firstRouter.equals(other._firstRouter) && _secondRouter.equals(other._secondRouter);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_firstRouter, _secondRouter);
  }

  @Override
  public String toString() {
    return guardName();
  }
}
