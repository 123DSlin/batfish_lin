package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import java.util.HashMap;
import java.util.Map;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Algebra of {@code SymbolicTrafficFraction} used by Algorithms 1 and 2. */
@RunWith(JUnit4.class)
public class SymbolicTrafficFractionTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Test
  public void testConstPlusTimesDiv() {
    SymbolicTrafficFraction half = new SymbolicTrafficFraction(0.5);
    assertThat(SymbolicTrafficFraction.one().plus(half), equalTo(new SymbolicTrafficFraction(1.5)));
    assertThat(half.times(4.0), equalTo(new SymbolicTrafficFraction(2.0)));
    assertThat(
        SymbolicTrafficFraction.one().div(new SymbolicTrafficFraction(4.0)).getValue(),
        closeTo(0.25, 1e-9));
  }

  @Test
  public void testDivByZeroIsZero() {
    assertThat(
        SymbolicTrafficFraction.one().div(SymbolicTrafficFraction.zero()).isZero(), equalTo(true));
  }

  @Test
  public void testZeroTimesAnythingIsZero() {
    assertThat(
        SymbolicTrafficFraction.zero()
            .times(SymbolicTrafficFraction.fromGuard(GUARDS.variable("g")))
            .isZero(),
        equalTo(true));
  }

  @Test
  public void testGuardEvaluatesToZeroOrOne() {
    SymbolicTrafficFraction g = SymbolicTrafficFraction.fromGuard(GUARDS.variable("x"));
    Map<String, Boolean> up = new HashMap<>();
    up.put("x", true);
    Map<String, Boolean> down = new HashMap<>();
    down.put("x", false);
    assertThat(g.evaluate(up), closeTo(1.0, 1e-9));
    assertThat(g.evaluate(down), closeTo(0.0, 1e-9));
    assertThat(SymbolicTrafficFraction.one().times(g).evaluate(up), closeTo(1.0, 1e-9));
  }

  @Test
  public void testTrueAndFalseAstFoldToConstants() {
    assertThat(SymbolicTrafficFraction.fromGuard(GUARDS.trueGuard()).isOne(), equalTo(true));
    assertThat(SymbolicTrafficFraction.fromGuard(GUARDS.falseGuard()).isZero(), equalTo(true));
    assertThat(
        SymbolicTrafficFraction.fromGuard(GUARDS.trueGuard().and(GUARDS.trueGuard().not()))
            .isZero(),
        equalTo(true));
  }

  @Test
  public void testAndNotOrEvaluate() {
    SymbolicTrafficFraction and =
        SymbolicTrafficFraction.fromGuard(GUARDS.variable("a").and(GUARDS.variable("b")));
    SymbolicTrafficFraction not = SymbolicTrafficFraction.fromGuard(GUARDS.variable("a").not());
    SymbolicTrafficFraction or =
        SymbolicTrafficFraction.fromGuard(GUARDS.variable("a").or(GUARDS.variable("b")));
    Map<String, Boolean> aOnly = new HashMap<>();
    aOnly.put("a", true);
    aOnly.put("b", false);
    assertThat(and.evaluate(aOnly), closeTo(0.0, 1e-9));
    assertThat(not.evaluate(aOnly), closeTo(0.0, 1e-9));
    assertThat(or.evaluate(aOnly), closeTo(1.0, 1e-9));
  }

  @Test
  public void testEvaluateDivByZeroAtAssignmentIsZero() {
    SymbolicTrafficFraction g = SymbolicTrafficFraction.fromGuard(GUARDS.variable("x"));
    Map<String, Boolean> down = new HashMap<>();
    down.put("x", false);
    assertThat(SymbolicTrafficFraction.one().div(g).evaluate(down), closeTo(0.0, 1e-9));
  }
}
