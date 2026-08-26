package org.batfish.minesweeper.symbolicroute;

/**
 * A representation-independent Boolean condition describing when a symbolic route is present.
 *
 * <p>Implementations may use Z3, BDDs, or another canonical Boolean representation. Symbolic-route
 * data structures depend only on this interface so the representation can evolve independently.
 */
public interface RouteGuard {

  RouteGuard and(RouteGuard other);

  RouteGuard or(RouteGuard other);

  RouteGuard not();

  RouteGuard simplify();

  /** Stronger, potentially more expensive equivalent simplification for reports only. */
  default RouteGuard simplifyForDisplay() {
    return simplify();
  }

  boolean isSatisfiable();

  boolean isEquivalentTo(RouteGuard other);

  boolean isTrue();

  boolean isFalse();
}
