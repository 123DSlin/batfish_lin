package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.Map;
import org.batfish.minesweeper.symbolicroute.BooleanGuardAst;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/**
 * One cell of {@code M[l, S]}. Algorithm 1 adds cells; Algorithm 2 fills them with {@code ω · c_r}
 * (constants, Boolean guards, sums, products, and the ECMP/SR quotients).
 */
public class SymbolicTrafficFraction {

  private enum Kind {
    CONST,
    GUARD,
    PLUS,
    TIMES,
    DIV
  }

  private static final SymbolicTrafficFraction ZERO = new SymbolicTrafficFraction(0.0);
  private static final SymbolicTrafficFraction ONE = new SymbolicTrafficFraction(1.0);

  private final Kind _kind;
  private final double _const;
  private final RouteGuard _guard;
  private final SymbolicTrafficFraction _left;
  private final SymbolicTrafficFraction _right;

  public SymbolicTrafficFraction(double value) {
    this(Kind.CONST, value, null, null, null);
  }

  private SymbolicTrafficFraction(
      Kind kind,
      double constant,
      RouteGuard guard,
      SymbolicTrafficFraction left,
      SymbolicTrafficFraction right) {
    _kind = kind;
    _const = constant;
    _guard = guard;
    _left = left;
    _right = right;
  }

  public static SymbolicTrafficFraction zero() {
    return ZERO;
  }

  public static SymbolicTrafficFraction one() {
    return ONE;
  }

  public static SymbolicTrafficFraction fromGuard(RouteGuard guard) {
    BooleanGuardAst ast = guard.getAst();
    if (ast.getOperator() == BooleanGuardAst.Operator.FALSE) {
      return zero();
    }
    if (ast.getOperator() == BooleanGuardAst.Operator.TRUE) {
      return one();
    }
    return new SymbolicTrafficFraction(Kind.GUARD, 0.0, guard, null, null);
  }

  public SymbolicTrafficFraction plus(SymbolicTrafficFraction other) {
    if (isZero()) {
      return other;
    }
    if (other.isZero()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const + other._const);
    }
    return new SymbolicTrafficFraction(Kind.PLUS, 0.0, null, this, other);
  }

  public SymbolicTrafficFraction times(SymbolicTrafficFraction other) {
    if (isZero() || other.isZero()) {
      return zero();
    }
    if (isOne()) {
      return other;
    }
    if (other.isOne()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const * other._const);
    }
    return new SymbolicTrafficFraction(Kind.TIMES, 0.0, null, this, other);
  }

  public SymbolicTrafficFraction times(double scalar) {
    return times(new SymbolicTrafficFraction(scalar));
  }

  public SymbolicTrafficFraction div(SymbolicTrafficFraction other) {
    if (isZero() || other.isZero()) {
      return zero();
    }
    if (other.isOne()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const / other._const);
    }
    return new SymbolicTrafficFraction(Kind.DIV, 0.0, null, this, other);
  }

  public boolean isZero() {
    if (_kind == Kind.CONST) {
      return _const == 0.0;
    }
    return _kind == Kind.GUARD
        && _guard.getAst().getOperator() == BooleanGuardAst.Operator.FALSE;
  }

  public boolean isOne() {
    return _kind == Kind.CONST && _const == 1.0;
  }

  public double getValue() {
    if (_kind != Kind.CONST) {
      throw new IllegalStateException("value is symbolic");
    }
    return _const;
  }

  /** Evaluate the formula at a Boolean assignment of guard variable ids. */
  public double evaluate(Map<String, Boolean> assignment) {
    switch (_kind) {
      case CONST:
        return _const;
      case GUARD:
        return evaluateAst(_guard.getAst(), assignment) ? 1.0 : 0.0;
      case PLUS:
        return _left.evaluate(assignment) + _right.evaluate(assignment);
      case TIMES:
        return _left.evaluate(assignment) * _right.evaluate(assignment);
      case DIV:
        double denominator = _right.evaluate(assignment);
        if (denominator == 0.0) {
          return 0.0;
        }
        return _left.evaluate(assignment) / denominator;
      default:
        throw new IllegalStateException("unsupported traffic-fraction kind");
    }
  }

  private static boolean evaluateAst(BooleanGuardAst ast, Map<String, Boolean> assignment) {
    switch (ast.getOperator()) {
      case TRUE:
        return true;
      case FALSE:
        return false;
      case VARIABLE:
        Boolean value = assignment.get(ast.getVariableId());
        if (value == null) {
          throw new IllegalArgumentException("no assignment for " + ast.getVariableId());
        }
        return value;
      case NOT:
        return !evaluateAst(ast.getChildren().get(0), assignment);
      case AND:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (!evaluateAst(child, assignment)) {
            return false;
          }
        }
        return true;
      case OR:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (evaluateAst(child, assignment)) {
            return true;
          }
        }
        return false;
      default:
        throw new IllegalArgumentException("unsupported guard operator");
    }
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicTrafficFraction)) {
      return false;
    }
    SymbolicTrafficFraction other = (SymbolicTrafficFraction) o;
    if (_kind != other._kind) {
      return false;
    }
    if (_kind == Kind.CONST) {
      return Double.compare(_const, other._const) == 0;
    }
    return false;
  }

  @Override
  public int hashCode() {
    if (_kind == Kind.CONST) {
      return Double.hashCode(_const);
    }
    return _kind.hashCode();
  }

  @Override
  public String toString() {
    switch (_kind) {
      case CONST:
        return Double.toString(_const);
      case GUARD:
        return _guard.toString();
      case PLUS:
        return "(" + _left + "+" + _right + ")";
      case TIMES:
        return "(" + _left + "*" + _right + ")";
      case DIV:
        return "(" + _left + "/" + _right + ")";
      default:
        return _kind.name();
    }
  }
}
