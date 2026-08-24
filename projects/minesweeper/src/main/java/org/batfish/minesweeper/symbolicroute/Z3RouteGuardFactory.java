package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.microsoft.z3.Context;
import javax.annotation.Nonnull;

/** Creates Z3-backed route guards that share one solver context. */
public final class Z3RouteGuardFactory {

  @Nonnull private final Context _context;

  public Z3RouteGuardFactory(Context context) {
    _context = requireNonNull(context, "context must be provided");
  }

  public Z3RouteGuard variable(String name) {
    return new Z3RouteGuard(_context, _context.mkBoolConst(name));
  }

  public Z3RouteGuard trueGuard() {
    return new Z3RouteGuard(_context, _context.mkTrue());
  }

  public Z3RouteGuard falseGuard() {
    return new Z3RouteGuard(_context, _context.mkFalse());
  }
}
