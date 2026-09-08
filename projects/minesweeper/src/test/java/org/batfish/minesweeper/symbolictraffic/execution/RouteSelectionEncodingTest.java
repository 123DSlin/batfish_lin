package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** YU route-selection encoding {@code s_r} and ECMP {@code c_r}. */
@RunWith(JUnit4.class)
public class RouteSelectionEncodingTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix DEST = Prefix.parse("5.5.5.5/32");
  private static final Ip DST_IP = DEST.getStartIp();

  private static ForwardingRule direct(RouteGuard guard, int preference) {
    return ForwardingRule.direct(
        DEST,
        guard,
        preference,
        new TrafficGraphEdge("a_b", "a", "b", "Ethernet0", "Ethernet0", 95.0, false));
  }

  @Test
  public void testNonMatchingRuleHasFalseSelection() {
    ForwardingRule rule = direct(GUARDS.variable("g"), 10);
    RouteGuard selected =
        RouteSelectionEncoding.selection(
            rule, Collections.singletonList(rule), Ip.parse("1.2.3.4"));
    assertThat(selected.isEquivalentTo(GUARDS.falseGuard()), equalTo(true));
  }

  @Test
  public void testWorseRouteRequiresBetterRouteAbsent() {
    RouteGuard gHigh = GUARDS.variable("g_high");
    RouteGuard gLow = GUARDS.variable("g_low");
    ForwardingRule high = direct(gHigh, 10);
    ForwardingRule low = direct(gLow, 20);
    List<ForwardingRule> rib = Arrays.asList(high, low);

    assertThat(
        RouteSelectionEncoding.selection(high, rib, DST_IP).isEquivalentTo(gHigh), equalTo(true));
    assertThat(
        RouteSelectionEncoding.selection(low, rib, DST_IP)
            .isEquivalentTo(gLow.and(gHigh.not())),
        equalTo(true));
  }

  @Test
  public void testEcmpSplitsOnlyAmongEquallyPreferredSelectedRules() {
    RouteGuard g1 = GUARDS.variable("g1");
    RouteGuard g2 = GUARDS.variable("g2");
    ForwardingRule r1 = direct(g1, 10);
    ForwardingRule r2 = direct(g2, 10);
    List<ForwardingRule> rib = Arrays.asList(r1, r2);
    SymbolicTrafficFraction c1 = RouteSelectionEncoding.ecmpRatio(r1, rib, DST_IP);
    SymbolicTrafficFraction c2 = RouteSelectionEncoding.ecmpRatio(r2, rib, DST_IP);

    Map<String, Boolean> both = new HashMap<>();
    both.put("g1", true);
    both.put("g2", true);
    assertThat(c1.evaluate(both), closeTo(0.5, 1e-9));
    assertThat(c2.evaluate(both), closeTo(0.5, 1e-9));

    Map<String, Boolean> onlyFirst = new HashMap<>();
    onlyFirst.put("g1", true);
    onlyFirst.put("g2", false);
    assertThat(c1.evaluate(onlyFirst), closeTo(1.0, 1e-9));
    assertThat(c2.evaluate(onlyFirst), closeTo(0.0, 1e-9));
  }

  @Test
  public void testLongerPrefixIsStrictlyPreferred() {
    RouteGuard gDefault = GUARDS.variable("g_def");
    RouteGuard gExact = GUARDS.variable("g_exact");
    ForwardingRule def =
        ForwardingRule.direct(
            Prefix.parse("0.0.0.0/0"),
            gDefault,
            10,
            new TrafficGraphEdge("a_b", "a", "b", "Ethernet0", "Ethernet0", 95.0, false));
    ForwardingRule exact = direct(gExact, 10);
    List<ForwardingRule> rib = Arrays.asList(def, exact);

    assertThat(RouteSelectionEncoding.strictlyPreferred(exact, def), equalTo(true));
    assertThat(RouteSelectionEncoding.strictlyPreferred(def, exact), equalTo(false));
    assertThat(
        RouteSelectionEncoding.selection(def, rib, DST_IP)
            .isEquivalentTo(gDefault.and(gExact.not())),
        equalTo(true));
  }

  @Test
  public void testEqualPreferenceIsNotStrictlyPreferred() {
    ForwardingRule r1 = direct(GUARDS.variable("a"), 10);
    ForwardingRule r2 = direct(GUARDS.variable("b"), 10);
    assertThat(RouteSelectionEncoding.strictlyPreferred(r1, r2), equalTo(false));
    assertThat(RouteSelectionEncoding.strictlyPreferred(r2, r1), equalTo(false));
  }

  @Test
  public void testThreePreferenceLevels() {
    RouteGuard g1 = GUARDS.variable("g1");
    RouteGuard g2 = GUARDS.variable("g2");
    RouteGuard g3 = GUARDS.variable("g3");
    ForwardingRule r1 = direct(g1, 10);
    ForwardingRule r2 = direct(g2, 20);
    ForwardingRule r3 = direct(g3, 30);
    List<ForwardingRule> rib = Arrays.asList(r1, r2, r3);
    assertThat(
        RouteSelectionEncoding.selection(r3, rib, DST_IP)
            .isEquivalentTo(g3.and(g1.not()).and(g2.not())),
        equalTo(true));
  }

  @Test
  public void testNoSelectedRouteYieldsZeroEcmpRatio() {
    ForwardingRule r1 = direct(GUARDS.falseGuard(), 10);
    SymbolicTrafficFraction c =
        RouteSelectionEncoding.ecmpRatio(r1, Collections.singletonList(r1), DST_IP);
    assertThat(c.evaluate(new HashMap<String, Boolean>()), closeTo(0.0, 1e-9));
  }

  @Test
  public void testThreeWayEcmp() {
    ForwardingRule r1 = direct(GUARDS.variable("g1"), 10);
    ForwardingRule r2 = direct(GUARDS.variable("g2"), 10);
    ForwardingRule r3 = direct(GUARDS.variable("g3"), 10);
    List<ForwardingRule> rib = Arrays.asList(r1, r2, r3);
    Map<String, Boolean> allUp = new HashMap<>();
    allUp.put("g1", true);
    allUp.put("g2", true);
    allUp.put("g3", true);
    assertThat(
        RouteSelectionEncoding.ecmpRatio(r1, rib, DST_IP).evaluate(allUp),
        closeTo(1.0 / 3.0, 1e-9));
    assertThat(
        RouteSelectionEncoding.ecmpRatio(r2, rib, DST_IP).evaluate(allUp),
        closeTo(1.0 / 3.0, 1e-9));
    assertThat(
        RouteSelectionEncoding.ecmpRatio(r3, rib, DST_IP).evaluate(allUp),
        closeTo(1.0 / 3.0, 1e-9));
  }
}
