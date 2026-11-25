package org.batfish.minesweeper.smt;

import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.equalTo;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import org.junit.Test;

public final class SymbolicPrefixLengthRangeTest {
  @Test
  public void testExactRuleCanBecomeRangeAndReturnToExact() {
    try (Context ctx = new Context()) {
      ArithExpr lower = ctx.mkIntConst("lower");
      ArithExpr upper = ctx.mkIntConst("upper");
      Solver solver = ctx.mkSolver();
      solver.add(EncoderSlice.symbolicPrefixLengthRange(ctx, ctx.mkInt(32), lower, upper));
      solver.push();
      solver.add(ctx.mkEq(lower, ctx.mkInt(0)), ctx.mkEq(upper, ctx.mkInt(32)));
      assertThat(solver.check(), equalTo(Status.SATISFIABLE));
      solver.pop();
      solver.push();
      solver.add(ctx.mkEq(lower, ctx.mkInt(24)), ctx.mkEq(upper, ctx.mkInt(24)));
      assertThat(solver.check(), equalTo(Status.UNSATISFIABLE));
      solver.pop();
      solver.add(ctx.mkEq(lower, ctx.mkInt(32)), ctx.mkEq(upper, ctx.mkInt(32)));
      assertThat(solver.check(), equalTo(Status.SATISFIABLE));
    }
  }
}
