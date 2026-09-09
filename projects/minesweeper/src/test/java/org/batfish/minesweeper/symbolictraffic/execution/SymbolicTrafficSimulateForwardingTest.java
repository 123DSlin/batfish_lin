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
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/**
 * End-to-end checks of YU Algorithm 1 {@code simulate(f)} using the real Algorithm 2 {@code
 * forward}, not the hop-loop stand-in.
 */
@RunWith(JUnit4.class)
public class SymbolicTrafficSimulateForwardingTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix DEST = Prefix.parse("5.5.5.5/32");
  private static final Ip NIP = Ip.parse("10.0.0.6");

  private static TrafficFlow ipFlow(String source) {
    return new TrafficFlow(
        source + "-to-d", source, DEST, 20.0, TrafficFlow.ForwardingType.IP, null, null);
  }

  private static TrafficGraphEdge edge(String id, String from, String to) {
    return new TrafficGraphEdge(id, from, to, "Ethernet0", "Ethernet0", 95.0, false);
  }

  private static TrafficGraph graph(TrafficFlow flow, TrafficGraphEdge... edges) {
    return new TrafficGraph(
        Arrays.asList("a", "b", "c", "d", "e", "f"),
        Arrays.asList(edges),
        Collections.singleton(flow));
  }

  @Test
  public void testLinearIpPathHopOneAndHopTwo() {
    TrafficFlow f = ipFlow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge bc = edge("b_c", "b", "c");
    TrafficGraph g = graph(f, ab, bc);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put(
        "a",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab)));
    ribs.put(
        "b",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, bc)));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forwarding).simulateHopI(f);
    assertThat(
        hop1.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(hop1.get(bc, TrafficLabelStack.empty()).isZero(), equalTo(true));

    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(
                g,
                2,
                new SymbolicTrafficForwarding(
                    g, ribs, Collections.emptyMap(), Collections.emptyMap()))
            .simulateHopI(f);
    assertThat(hop2.get(ab, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(
        hop2.get(bc, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));

    SymbolicTrafficMatrix hop3 =
        new SymbolicTrafficExecution(
                g,
                3,
                new SymbolicTrafficForwarding(
                    g, ribs, Collections.emptyMap(), Collections.emptyMap()))
            .simulateHopI(f);
    assertThat(hop3.isZero(), equalTo(true));

    SymbolicTrafficMatrix accumulated =
        new SymbolicTrafficExecution(
                g,
                255,
                new SymbolicTrafficForwarding(
                    g, ribs, Collections.emptyMap(), Collections.emptyMap()))
            .simulate(f);
    assertThat(
        accumulated.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(1.0, 1e-9));
    assertThat(
        accumulated.get(bc, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(1.0, 1e-9));
  }

  @Test
  public void testPreferenceFailoverAtFirstHop() {
    TrafficFlow f = ipFlow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put(
        "a",
        Arrays.asList(
            ForwardingRule.direct(DEST, GUARDS.variable("g_high"), 10, ab),
            ForwardingRule.direct(DEST, GUARDS.variable("g_low"), 20, ac)));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());
    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forwarding).simulateHopI(f);
    Map<String, Boolean> bothUp = new HashMap<>();
    bothUp.put("g_high", true);
    bothUp.put("g_low", true);
    assertThat(hop1.get(ab, TrafficLabelStack.empty()).evaluate(bothUp), closeTo(1.0, 1e-9));
    assertThat(hop1.get(ac, TrafficLabelStack.empty()).evaluate(bothUp), closeTo(0.0, 1e-9));

    Map<String, Boolean> preferredDown = new HashMap<>();
    preferredDown.put("g_high", false);
    preferredDown.put("g_low", true);
    assertThat(
        hop1.get(ab, TrafficLabelStack.empty()).evaluate(preferredDown), closeTo(0.0, 1e-9));
    assertThat(
        hop1.get(ac, TrafficLabelStack.empty()).evaluate(preferredDown), closeTo(1.0, 1e-9));
  }

  @Test
  public void testEcmpDiamondSecondHopSplitsOnEachBranch() {
    TrafficFlow f = ipFlow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraphEdge bd = edge("b_d", "b", "d");
    TrafficGraphEdge cd = edge("c_d", "c", "d");
    TrafficGraph g = graph(f, ab, ac, bd, cd);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put(
        "a",
        Arrays.asList(
            ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab),
            ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ac)));
    ribs.put(
        "b",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, bd)));
    ribs.put(
        "c",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, cd)));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix hop1 = new SymbolicTrafficExecution(g, 1, forwarding).simulateHopI(f);
    assertThat(
        hop1.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));
    assertThat(
        hop1.get(ac, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));

    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(
                g,
                2,
                new SymbolicTrafficForwarding(
                    g, ribs, Collections.emptyMap(), Collections.emptyMap()))
            .simulateHopI(f);
    assertThat(
        hop2.get(bd, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));
    assertThat(
        hop2.get(cd, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));

    SymbolicTrafficMatrix accumulated =
        new SymbolicTrafficExecution(
                g,
                255,
                new SymbolicTrafficForwarding(
                    g, ribs, Collections.emptyMap(), Collections.emptyMap()))
            .simulate(f);
    assertThat(
        accumulated.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(0.5, 1e-9));
    assertThat(
        accumulated.get(ac, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(0.5, 1e-9));
    assertThat(
        accumulated.get(bd, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(0.5, 1e-9));
    assertThat(
        accumulated.get(cd, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(0.5, 1e-9));
  }

  @Test
  public void testSrPushThenNextHopKeepsRemainder() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraphEdge ef = edge("e_f", "e", "f");
    TrafficGraph g = graph(f, de, ef);
    Prefix ePrefix = Prefix.parse("10.0.0.5/32");
    Prefix fPrefix = Prefix.parse("10.0.0.6/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igpDe = ForwardingRule.direct(ePrefix, GUARDS.trueGuard(), 10, de);
    ForwardingRule igpEf = ForwardingRule.direct(fPrefix, GUARDS.trueGuard(), 10, ef);
    SrPolicy.Path path = new SrPolicy.Path(GUARDS.trueGuard(), 1, Arrays.asList("e", "f"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Arrays.asList(bgp, igpDe));
    ribs.put("e", Collections.singletonList(igpEf));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", ePrefix.getStartIp());
    addresses.put("f", fPrefix.getStartIp());

    TrafficLabelStack pushed = path.toStack();
    TrafficLabelStack remainder = TrafficLabelStack.nodes("f");

    SymbolicTrafficMatrix hop1 =
        new SymbolicTrafficExecution(
                g, 1, new SymbolicTrafficForwarding(g, ribs, policies, addresses))
            .simulateHopI(f);
    assertThat(hop1.get(de, pushed).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(hop1.get(de, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(hop1.get(ef, remainder).isZero(), equalTo(true));

    SymbolicTrafficMatrix hop2 =
        new SymbolicTrafficExecution(
                g, 2, new SymbolicTrafficForwarding(g, ribs, policies, addresses))
            .simulateHopI(f);
    assertThat(hop2.get(ef, remainder).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(hop2.get(ef, pushed).isZero(), equalTo(true));
    assertThat(hop2.get(ef, TrafficLabelStack.empty()).isZero(), equalTo(true));

    SymbolicTrafficMatrix accumulated =
        new SymbolicTrafficExecution(
                g, 255, new SymbolicTrafficForwarding(g, ribs, policies, addresses))
            .simulate(f);
    assertThat(accumulated.get(de, pushed).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(accumulated.get(ef, remainder).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testTerminalLocalRouteAbsorbsMassAndDoesNotLoop() {
    TrafficFlow f = ipFlow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ba = edge("b_a", "b", "a");
    TrafficGraph g = graph(f, ab, ba);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put(
        "a",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab)));
    ribs.put(
        "b",
        Arrays.asList(
            ForwardingRule.terminal(DEST, GUARDS.trueGuard(), 0),
            ForwardingRule.direct(DEST, GUARDS.trueGuard(), 115, ba)));
    SymbolicTrafficExecution execution =
        new SymbolicTrafficExecution(
            g,
            255,
            new SymbolicTrafficForwarding(
                g, ribs, Collections.emptyMap(), Collections.emptyMap()));
    SymbolicTrafficMatrix accumulated = execution.simulate(f);
    assertThat(
        accumulated.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()),
        closeTo(1.0, 1e-9));
    assertThat(accumulated.get(ba, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(execution.getLastCompletedHops() < 10, equalTo(true));
  }

  @Test
  public void testK1ExecutionPrintsYuStyleCompactStf() {
    TrafficFlow f = ipFlow("x");
    TrafficGraphEdge xd = edge("d_x", "x", "d");
    TrafficGraphEdge dx = edge("d_x", "d", "x");
    TrafficGraphEdge xa = edge("a_x", "x", "a");
    TrafficGraphEdge ax = edge("a_x", "a", "x");
    TrafficGraphEdge ad = edge("a_d", "a", "d");
    TrafficGraphEdge da = edge("a_d", "d", "a");
    TrafficGraph g =
        new TrafficGraph(
            Arrays.asList("x", "a", "d"),
            Arrays.asList(xd, dx, xa, ax, ad, da),
            Collections.singleton(f),
            1);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put(
        "x",
        Arrays.asList(
            ForwardingRule.direct(DEST, GUARDS.variable("d_x"), 10, xd),
            ForwardingRule.direct(
                DEST, GUARDS.variable("d_x").not().and(GUARDS.variable("a_x")), 20, xa)));
    ribs.put(
        "a",
        Collections.singletonList(ForwardingRule.direct(DEST, GUARDS.variable("a_d"), 10, ad)));
    ribs.put("d", Collections.singletonList(ForwardingRule.terminal(DEST, GUARDS.trueGuard(), 0)));
    SymbolicTrafficExecution execution =
        new SymbolicTrafficExecution(
            g,
            255,
            new SymbolicTrafficForwarding(
                g, ribs, Collections.emptyMap(), Collections.emptyMap()));
    SymbolicTrafficMatrix matrix = execution.simulate(f);
    assertThat(matrix.get(xd, TrafficLabelStack.empty()).toDisplayString(64), equalTo("d_x"));
    assertThat(
        matrix.get(xa, TrafficLabelStack.empty()).toDisplayString(64), equalTo("(not d_x)"));
    assertThat(
        matrix.get(ad, TrafficLabelStack.empty()).toDisplayString(64), equalTo("(not d_x)"));
    assertThat(matrix.get(ax, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(matrix.get(da, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(execution.getLastCompletedHops() < 10, equalTo(true));
  }
}
