package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import javax.annotation.Nonnull;

/** Creates Z3-backed route guards that share one solver context. */
public final class Z3RouteGuardFactory {

  @Nonnull private final Context _context;

  public Z3RouteGuardFactory(Context context) {
    _context = requireNonNull(context, "context must be provided");
  }

  public Z3RouteGuard variable(String name) {
    String checked = requireNonNull(name, "name must be provided");
    return new Z3RouteGuard(
        _context, _context.mkBoolConst(checked), BooleanGuardAst.variable(checked));
  }

  public Z3RouteGuard trueGuard() {
    return new Z3RouteGuard(_context, _context.mkTrue(), BooleanGuardAst.trueValue());
  }

  public Z3RouteGuard falseGuard() {
    return new Z3RouteGuard(_context, _context.mkFalse(), BooleanGuardAst.falseValue());
  }

  /** Compiles a persisted solver-independent guard into this factory's Z3 context. */
  public Z3RouteGuard fromAst(BooleanGuardAst ast) {
    BooleanGuardAst checked = requireNonNull(ast, "ast must be provided");
    return new Z3RouteGuard(_context, compile(checked), checked);
  }

  private BoolExpr compile(BooleanGuardAst ast) {
    switch (ast.getOperator()) {
      case TRUE:
        return _context.mkTrue();
      case FALSE:
        return _context.mkFalse();
      case VARIABLE:
        return _context.mkBoolConst(ast.getVariableId());
      case NOT:
        return _context.mkNot(compile(ast.getChildren().get(0)));
      case AND:
        return _context.mkAnd(
            ast.getChildren().stream().map(this::compile).toArray(BoolExpr[]::new));
      case OR:
        return _context.mkOr(
            ast.getChildren().stream().map(this::compile).toArray(BoolExpr[]::new));
      default:
        throw new IllegalArgumentException("unsupported Boolean guard operator");
    }
  }
}
