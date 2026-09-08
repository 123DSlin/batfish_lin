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
    assertThat(selected.isFalse(), equalTo(true));
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
    assertThat(
        RouteSelectionEncoding.selection(def, rib, DST_IP)
            .isEquivalentTo(gDefault.and(gExact.not())),
        equalTo(true));
  }
}
