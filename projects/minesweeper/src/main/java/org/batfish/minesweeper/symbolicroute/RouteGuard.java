package org.batfish.minesweeper.symbolicroute;

/**
 * A representation-independent Boolean condition describing when a symbolic route is present.
 *
 * <p>Implementations may use Z3, BDDs, or another canonical Boolean representation. Symbolic-route
 * data structures depend only on this interface so the representation can evolve independently.
 */
public interface RouteGuard {

  /** Solver-independent syntax tree suitable for persistence and reconstruction. */
  BooleanGuardAst getAst();

  RouteGuard and(RouteGuard other);

  /** Conjoin a persisted predicate using this guard's own solver/context. */
  default RouteGuard andAst(BooleanGuardAst other) {
    throw new UnsupportedOperationException("guard does not support persisted predicates");
  }

  RouteGuard or(RouteGuard other);

  RouteGuard not();

  RouteGuard simplify();

  /** Stronger, potentially more expensive equivalent simplification for reports only. */
  default RouteGuard simplifyForDisplay() {
    return simplify();
  }

  boolean isSatisfiable();

  /** Satisfiable after fixing every embedded integer Config_* atom to its snapshot seed. */
  default boolean isSatisfiableAtConfigurationPins() {
    return isSatisfiable();
  }

  boolean isEquivalentTo(RouteGuard other);

  boolean isTrue();

  boolean isFalse();
}
