package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.lessThan;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import java.util.HashMap;
import java.util.List;
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
  public void testComplementaryLiteralsFoldToZero() {
    SymbolicTrafficFraction xAndNotX =
        SymbolicTrafficFraction.fromGuard(GUARDS.variable("x").and(GUARDS.variable("x").not()));
    SymbolicTrafficFraction nested =
        SymbolicTrafficFraction.fromGuard(
            GUARDS.trueGuard().and(GUARDS.variable("d_x")).not().and(GUARDS.variable("d_x")));
    assertThat(xAndNotX.isZero(), equalTo(true));
    assertThat(nested.isZero(), equalTo(true));
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

  @Test
  public void testGuardToStringUsesAstNotZ3() {
    assertThat(SymbolicTrafficFraction.fromGuard(GUARDS.variable("x")).toString(), equalTo("x"));
    assertThat(
        SymbolicTrafficFraction.fromGuard(GUARDS.variable("a").and(GUARDS.variable("b"))).toString(),
        equalTo("(a and b)"));
  }

  @Test
  public void testSharedDagDoesNotUnfoldToExponentialString() {
    SymbolicTrafficFraction acc = SymbolicTrafficFraction.fromGuard(GUARDS.variable("x"));
    for (int i = 0; i < 40; i++) {
      acc = acc.plus(acc);
    }
    assertThat(acc.toString().length(), lessThan(4000));
    @SuppressWarnings("unchecked")
    Map<String, Object> json = (Map<String, Object>) acc.toJsonValue();
    assertThat((List<?>) json.get("nodes"), hasSize(41));
  }

  @Test
  public void testKReduce0IsAllUpConstant() {
    SymbolicTrafficFraction g = SymbolicTrafficFraction.fromGuard(GUARDS.variable("d_x"));
    assertThat(g.kReduce(0, java.util.Collections.singleton("d_x")).isOne(), equalTo(true));
  }

  @Test
  public void testKReduce1PreferredLinkIsTheVariable() {
    SymbolicTrafficFraction g = SymbolicTrafficFraction.fromGuard(GUARDS.variable("d_x"));
    SymbolicTrafficFraction reduced = g.kReduce(1, java.util.Arrays.asList("d_x", "a_d"));
    assertThat(reduced.toDisplayString(64), equalTo("d_x"));
    Map<String, Boolean> dxDown = new HashMap<>();
    dxDown.put("d_x", false);
    dxDown.put("a_d", true);
    assertThat(reduced.evaluate(dxDown), closeTo(0.0, 1e-9));
  }

  @Test
  public void testKReduce1FailoverIsNotOfPreferred() {
    SymbolicTrafficFraction failover =
        SymbolicTrafficFraction.fromGuard(GUARDS.variable("d_x").not());
    SymbolicTrafficFraction reduced =
        failover.kReduce(1, java.util.Arrays.asList("d_x", "a_d", "a_x"));
    assertThat(reduced.toDisplayString(64), equalTo("(not d_x)"));
    Map<String, Boolean> dxDown = new HashMap<>();
    dxDown.put("d_x", false);
    dxDown.put("a_d", true);
    dxDown.put("a_x", true);
    assertThat(reduced.evaluate(dxDown), closeTo(1.0, 1e-9));
    assertThat(reduced.evaluateAllUp(), closeTo(0.0, 1e-9));
  }

  @Test
  public void testKReduceAgreesOnYuFigure5K1Slice() {
    // Figure 5: 1*x1 + 0.5*¬x1¬x2¬x3. For k=1 the 3-failure term drops; KREDUCE is x1.
    SymbolicTrafficFraction x1 = SymbolicTrafficFraction.fromGuard(GUARDS.variable("x1"));
    SymbolicTrafficFraction nots =
        SymbolicTrafficFraction.fromGuard(
            GUARDS.variable("x1").not().and(GUARDS.variable("x2").not()).and(GUARDS.variable("x3").not()));
    SymbolicTrafficFraction figure5 = x1.plus(new SymbolicTrafficFraction(0.5).times(nots));
    SymbolicTrafficFraction reduced =
        figure5.kReduce(1, java.util.Arrays.asList("x1", "x2", "x3"));
    Map<String, Boolean> allUp = new HashMap<>();
    allUp.put("x1", true);
    allUp.put("x2", true);
    allUp.put("x3", true);
    Map<String, Boolean> x1Down = new HashMap<>(allUp);
    x1Down.put("x1", false);
    Map<String, Boolean> x2Down = new HashMap<>(allUp);
    x2Down.put("x2", false);
    assertThat(reduced.evaluate(allUp), closeTo(1.0, 1e-9));
    assertThat(reduced.evaluate(x1Down), closeTo(0.0, 1e-9));
    assertThat(reduced.evaluate(x2Down), closeTo(1.0, 1e-9));
    assertThat(figure5.evaluate(allUp), closeTo(reduced.evaluate(allUp), 1e-9));
    assertThat(figure5.evaluate(x1Down), closeTo(reduced.evaluate(x1Down), 1e-9));
    assertThat(figure5.evaluate(x2Down), closeTo(reduced.evaluate(x2Down), 1e-9));
  }
}
