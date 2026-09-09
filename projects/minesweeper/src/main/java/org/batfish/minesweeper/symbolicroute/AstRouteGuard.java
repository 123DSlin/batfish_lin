package org.batfish.minesweeper.symbolicroute;

/**
 * Solver-free {@link RouteGuard} over a {@link BooleanGuardAst}. Used by traffic SMT encoding when
 * Z3 is not required (AllUp collapse, kReduce AST leaves).
 */
public final class AstRouteGuard implements RouteGuard {

  private final BooleanGuardAst _ast;

  public AstRouteGuard(BooleanGuardAst ast) {
    if (ast == null) {
      throw new IllegalArgumentException("guard AST cannot be null");
    }
    _ast = ast;
  }

  public static AstRouteGuard alwaysTrue() {
    return new AstRouteGuard(BooleanGuardAst.trueValue());
  }

  public static AstRouteGuard alwaysFalse() {
    return new AstRouteGuard(BooleanGuardAst.falseValue());
  }

  @Override
  public BooleanGuardAst getAst() {
    return _ast;
  }

  @Override
  public RouteGuard and(RouteGuard other) {
    return new AstRouteGuard(BooleanGuardAst.and(_ast, other.getAst()));
  }

  @Override
  public RouteGuard or(RouteGuard other) {
    return new AstRouteGuard(BooleanGuardAst.or(_ast, other.getAst()));
  }

  @Override
  public RouteGuard not() {
    return new AstRouteGuard(BooleanGuardAst.not(_ast));
  }

  @Override
  public RouteGuard simplify() {
    return this;
  }

  @Override
  public boolean isSatisfiable() {
    return !isFalse();
  }

  @Override
  public boolean isEquivalentTo(RouteGuard other) {
    return _ast.equals(other.getAst());
  }

  @Override
  public boolean isTrue() {
    return _ast.getOperator() == BooleanGuardAst.Operator.TRUE;
  }

  @Override
  public boolean isFalse() {
    return _ast.getOperator() == BooleanGuardAst.Operator.FALSE;
  }
}
