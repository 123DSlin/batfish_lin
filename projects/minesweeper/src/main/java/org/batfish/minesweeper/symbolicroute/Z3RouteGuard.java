package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Goal;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import com.microsoft.z3.Tactic;
import java.util.ArrayList;
import java.util.BitSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nonnull;

/** A {@link RouteGuard} backed by a Z3 Boolean expression. */
public final class Z3RouteGuard implements RouteGuard {

  /** Keep exact display minimization bounded; larger guards retain the solver simplification. */
  private static final int DISPLAY_MINIMIZATION_MAX_VARIABLES = 10;

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
  public RouteGuard withAst(BooleanGuardAst ast) {
    return new Z3RouteGuardFactory(_context).fromAst(ast);
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
    List<String> variables = new ArrayList<>(_ast.getVariables());
    if (variables.size() <= DISPLAY_MINIMIZATION_MAX_VARIABLES) {
      return withAst(minimizeExactDnf(_ast, variables));
    }
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

  /** Exact small-guard DNF minimization; it changes only syntax, never failure semantics. */
  private static BooleanGuardAst minimizeExactDnf(BooleanGuardAst ast, List<String> variables) {
    int assignments = 1 << variables.size();
    BitSet onSet = new BitSet(assignments);
    for (int assignment = 0; assignment < assignments; assignment++) {
      if (evaluateAst(ast, variables, assignment)) {
        onSet.set(assignment);
      }
    }
    if (onSet.isEmpty()) {
      return BooleanGuardAst.falseValue();
    }
    if (onSet.cardinality() == assignments) {
      return BooleanGuardAst.trueValue();
    }
    List<Implicant> candidates = new ArrayList<>();
    enumerateImplicants(onSet, 0, new int[variables.size()], candidates);
    List<Implicant> prime = new ArrayList<>();
    for (Implicant candidate : candidates) {
      boolean subsumed = false;
      for (Implicant other : candidates) {
        if (candidate != other && other.strictlySubsumes(candidate)) {
          subsumed = true;
          break;
        }
      }
      if (!subsumed) {
        prime.add(candidate);
      }
    }
    BitSet uncovered = (BitSet) onSet.clone();
    List<BooleanGuardAst> terms = new ArrayList<>();
    while (!uncovered.isEmpty()) {
      Implicant best = null;
      int bestCoverage = -1;
      for (Implicant candidate : prime) {
        BitSet coverage = (BitSet) candidate._covered.clone();
        coverage.and(uncovered);
        int count = coverage.cardinality();
        if (count > bestCoverage
            || (count == bestCoverage
                && best != null
                && candidate.literalCount() < best.literalCount())) {
          best = candidate;
          bestCoverage = count;
        }
      }
      if (best == null || bestCoverage == 0) {
        throw new IllegalStateException("exact guard minimizer failed to cover an on-set assignment");
      }
      terms.add(best.toAst(variables));
      uncovered.andNot(best._covered);
    }
    return BooleanGuardAst.or(terms);
  }

  private static void enumerateImplicants(
      BitSet onSet, int index, int[] values, List<Implicant> result) {
    if (index == values.length) {
      Implicant candidate = Implicant.from(values, onSet);
      if (candidate != null) {
        result.add(candidate);
      }
      return;
    }
    for (int value = -1; value <= 1; value++) {
      values[index] = value;
      enumerateImplicants(onSet, index + 1, values, result);
    }
  }

  private static boolean evaluateAst(BooleanGuardAst ast, List<String> variables, int assignment) {
    switch (ast.getOperator()) {
      case TRUE:
        return true;
      case FALSE:
        return false;
      case VARIABLE:
        return (assignment & (1 << variables.indexOf(ast.getVariableId()))) != 0;
      case NOT:
        return !evaluateAst(ast.getChildren().get(0), variables, assignment);
      case AND:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (!evaluateAst(child, variables, assignment)) {
            return false;
          }
        }
        return true;
      case OR:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (evaluateAst(child, variables, assignment)) {
            return true;
          }
        }
        return false;
      default:
        throw new IllegalArgumentException("unsupported Boolean guard operator");
    }
  }

  private static final class Implicant {
    private final int[] _values;
    private final BitSet _covered;

    private Implicant(int[] values, BitSet covered) {
      _values = values;
      _covered = covered;
    }

    private static Implicant from(int[] values, BitSet onSet) {
      BitSet covered = new BitSet();
      int assignments = 1 << values.length;
      for (int assignment = 0; assignment < assignments; assignment++) {
        boolean matches = true;
        for (int index = 0; index < values.length; index++) {
          if (values[index] != -1
              && ((assignment & (1 << index)) != 0) != (values[index] == 1)) {
            matches = false;
            break;
          }
        }
        if (matches) {
          if (!onSet.get(assignment)) {
            return null;
          }
          covered.set(assignment);
        }
      }
      return covered.isEmpty() ? null : new Implicant(values.clone(), covered);
    }

    private boolean strictlySubsumes(Implicant other) {
      boolean moreGeneral = false;
      for (int index = 0; index < _values.length; index++) {
        if (_values[index] == -1 && other._values[index] != -1) {
          moreGeneral = true;
        } else if (_values[index] != other._values[index]) {
          return false;
        }
      }
      return moreGeneral;
    }

    private int literalCount() {
      int result = 0;
      for (int value : _values) {
        if (value != -1) {
          result++;
        }
      }
      return result;
    }

    private BooleanGuardAst toAst(List<String> variables) {
      List<BooleanGuardAst> literals = new ArrayList<>();
      for (int index = 0; index < _values.length; index++) {
        if (_values[index] == -1) {
          continue;
        }
        BooleanGuardAst variable = BooleanGuardAst.variable(variables.get(index));
        literals.add(_values[index] == 1 ? variable : BooleanGuardAst.not(variable));
      }
      return BooleanGuardAst.and(literals);
    }
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
