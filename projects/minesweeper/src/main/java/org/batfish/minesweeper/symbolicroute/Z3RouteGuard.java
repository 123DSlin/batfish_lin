package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Goal;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import com.microsoft.z3.Tactic;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nonnull;

/** A {@link RouteGuard} backed by a Z3 Boolean expression. */
public final class Z3RouteGuard implements RouteGuard {

  @Nonnull private final Context _context;
  @Nonnull private final BoolExpr _expression;
  @Nonnull private final BooleanGuardAst _ast;

  Z3RouteGuard(Context context, BoolExpr expression, BooleanGuardAst ast) {
    _context = requireNonNull(context, "context must be provided");
    _expression = requireNonNull(expression, "expression must be provided");
    _ast = requireNonNull(ast, "ast must be provided");
  }

  @Override
  public BooleanGuardAst getAst() {
    return _ast;
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
    Z3RouteGuard checkedOther = checked(other);
    return new Z3RouteGuard(
        _context,
        _context.mkAnd(_expression, checkedOther._expression),
        BooleanGuardAst.and(_ast, checkedOther._ast));
  }

  @Override
  public RouteGuard or(RouteGuard other) {
    Z3RouteGuard checkedOther = checked(other);
    return new Z3RouteGuard(
        _context,
        _context.mkOr(_expression, checkedOther._expression),
        BooleanGuardAst.or(_ast, checkedOther._ast));
  }

  @Override
  public RouteGuard not() {
    return new Z3RouteGuard(_context, _context.mkNot(_expression), BooleanGuardAst.not(_ast));
  }

  @Override
  public RouteGuard simplify() {
    return new Z3RouteGuard(_context, (BoolExpr) _expression.simplify(), _ast);
  }

  @Override
  public RouteGuard simplifyForDisplay() {
    Goal goal = _context.mkGoal(false, false, false);
    goal.add(_expression);
    Tactic tactic =
        _context.then(
            _context.mkTactic("simplify"),
            _context.mkTactic("ctx-solver-simplify"),
            _context.mkTactic("propagate-values"),
            _context.mkTactic("simplify"));
    Goal[] subgoals = tactic.apply(goal).getSubgoals();
    if (subgoals.length != 1) {
      return simplify();
    }
    return new Z3RouteGuard(_context, (BoolExpr) subgoals[0].AsBoolExpr().simplify(), _ast);
  }

  @Override
  public boolean isSatisfiable() {
    Solver solver = _context.mkSolver();
    solver.add(_expression);
    return solver.check() == Status.SATISFIABLE;
  }

  /**
   * Returns whether this guard is satisfiable when at most {@code maximumFailures} link-up
   * variables are false.
   */
  public boolean isSatisfiableWithAtMostFailures(Set<String> linkUpVariables, int maximumFailures) {
    requireNonNull(linkUpVariables, "linkUpVariables must be provided");
    if (maximumFailures < 0) {
      throw new IllegalArgumentException("maximumFailures must be nonnegative");
    }
    ArithExpr failures = _context.mkInt(0);
    for (String variable : linkUpVariables) {
      BoolExpr linkUp = _context.mkBoolConst(requireNonNull(variable, "link variable is null"));
      failures =
          _context.mkAdd(
              failures, (ArithExpr) _context.mkITE(linkUp, _context.mkInt(0), _context.mkInt(1)));
    }
    Solver solver = _context.mkSolver();
    solver.add(_expression);
    solver.add(_context.mkLe(failures, _context.mkInt(maximumFailures)));
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
    return _expression.isTrue()
        || isEquivalentTo(
            new Z3RouteGuard(_context, _context.mkTrue(), BooleanGuardAst.trueValue()));
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
