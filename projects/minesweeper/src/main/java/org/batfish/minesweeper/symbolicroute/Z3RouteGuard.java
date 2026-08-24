package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import java.util.Objects;
import javax.annotation.Nonnull;

/** A {@link RouteGuard} backed by a Z3 Boolean expression. */
public final class Z3RouteGuard implements RouteGuard {

  @Nonnull private final Context _context;
  @Nonnull private final BoolExpr _expression;

  Z3RouteGuard(Context context, BoolExpr expression) {
    _context = requireNonNull(context, "context must be provided");
    _expression = requireNonNull(expression, "expression must be provided");
  }

  private Z3RouteGuard checked(RouteGuard other) {
    if (!(other instanceof Z3RouteGuard)) {
      throw new IllegalArgumentException("guard implementations must match");
    }
    Z3RouteGuard z3Other = (Z3RouteGuard) other;
    if (!z3Other._context.equals(_context)) {
      throw new IllegalArgumentException("guards must belong to the same Z3 context");
    }
    return z3Other;
  }

  @Override
  public RouteGuard and(RouteGuard other) {
    return new Z3RouteGuard(_context, _context.mkAnd(_expression, checked(other)._expression));
  }

  @Override
  public RouteGuard or(RouteGuard other) {
    return new Z3RouteGuard(_context, _context.mkOr(_expression, checked(other)._expression));
  }

  @Override
  public RouteGuard not() {
    return new Z3RouteGuard(_context, _context.mkNot(_expression));
  }

  @Override
  public RouteGuard simplify() {
    return new Z3RouteGuard(_context, (BoolExpr) _expression.simplify());
  }

  @Override
  public boolean isSatisfiable() {
    Solver solver = _context.mkSolver();
    solver.add(_expression);
    return solver.check() == Status.SATISFIABLE;
  }

  @Override
  public boolean isEquivalentTo(RouteGuard other) {
    Z3RouteGuard z3Other = checked(other);
    Solver solver = _context.mkSolver();
    solver.add(_context.mkXor(_expression, z3Other._expression));
    return solver.check() == Status.UNSATISFIABLE;
  }

  @Override
  public boolean isTrue() {
    return _expression.isTrue() || isEquivalentTo(new Z3RouteGuard(_context, _context.mkTrue()));
  }

  @Override
  public boolean isFalse() {
    if (_expression.isFalse()) {
      return true;
    }
    Solver solver = _context.mkSolver();
    solver.add(_expression);
    return solver.check() == Status.UNSATISFIABLE;
  }

  @Nonnull
  public BoolExpr getExpression() {
    return _expression;
  }

  @Override
  public boolean equals(Object o) {
    return this == o
        || o instanceof Z3RouteGuard
            && _context.equals(((Z3RouteGuard) o)._context)
            && _expression.equals(((Z3RouteGuard) o)._expression);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_context, _expression);
  }

  @Override
  public String toString() {
    return _expression.toString();
  }
}
