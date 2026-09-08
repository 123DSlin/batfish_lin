package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
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

/** YU Algorithm 2 {@code forward} / {@code forwardIp} / {@code resolveNhIp} / {@code forwardSr}. */
@RunWith(JUnit4.class)
public class SymbolicTrafficForwardingTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix DEST = Prefix.parse("5.5.5.5/32");
  private static final Ip NIP = Ip.parse("10.0.0.6");

  private static TrafficFlow flow(String source) {
    return new TrafficFlow(
        source + "-to-d", source, DEST, 20.0, TrafficFlow.ForwardingType.IP, null, null);
  }

  private static TrafficGraphEdge edge(String id, String from, String to) {
    return new TrafficGraphEdge(id, from, to, "Ethernet0", "Ethernet0", 95.0, false);
  }

  private static TrafficGraph graph(TrafficFlow flow, TrafficGraphEdge... edges) {
    return new TrafficGraph(
        java.util.Arrays.asList("a", "b", "c", "d", "e", "f"),
        java.util.Arrays.asList(edges),
        Collections.singleton(flow));
  }

  @Test
  public void testForwardIpDirectNextHopUsesEcmpShare() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    ForwardingRule rule = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", Collections.singletonList(rule));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testForwardIpPrefersBetterRouteWhenBothPresent() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    ForwardingRule high = ForwardingRule.direct(DEST, GUARDS.variable("g_high"), 10, ab);
    ForwardingRule low = ForwardingRule.direct(DEST, GUARDS.variable("g_low"), 20, ac);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", java.util.Arrays.asList(high, low));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    Map<String, Boolean> both = new HashMap<>();
    both.put("g_high", true);
    both.put("g_low", true);
    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(matrix.get(ab, TrafficLabelStack.empty()).evaluate(both), closeTo(1.0, 1e-9));
    assertThat(matrix.get(ac, TrafficLabelStack.empty()).evaluate(both), closeTo(0.0, 1e-9));
  }

  @Test
  public void testResolveNhIpUsesVigpOnEmptyStack() {
    TrafficFlow f = flow("d");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix nipPrefix = Prefix.parse("10.0.0.6/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igp = ForwardingRule.direct(nipPrefix, GUARDS.trueGuard(), 10, de);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testResolveNhIpMatchingSrPolicyPushesStack() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix firstPrefix = Prefix.parse("10.0.0.5/32");
    ForwardingRule igp = ForwardingRule.direct(firstPrefix, GUARDS.trueGuard(), 10, de);
    SrPolicy.Path path =
        new SrPolicy.Path(GUARDS.trueGuard(), 1, java.util.Arrays.asList("e", "f"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(igp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", firstPrefix.getStartIp());
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    TrafficLabelStack stack = path.toStack();
    assertThat(matrix.get(de, stack).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(de, TrafficLabelStack.empty()).isZero(), equalTo(true));
  }

  @Test
  public void testForwardSrPopsWhenCurrentRouterIsStackTop() {
    TrafficFlow f = flow("e");
    TrafficGraphEdge ef = edge("e_f", "e", "f");
    TrafficGraph g = graph(f, ef);
    ForwardingRule ip = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ef);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("e", Collections.singletonList(ip));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    TrafficLabelStack stack = TrafficLabelStack.nodes("e");
    SymbolicTrafficMatrix matrix =
        forwarding.forward("e", f, stack, SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(ef, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testForwardSrKeepsStackAndUsesVigpTowardTop() {
    TrafficFlow f = flow("d");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix firstPrefix = Prefix.parse("10.0.0.5/32");
    ForwardingRule igp = ForwardingRule.direct(firstPrefix, GUARDS.trueGuard(), 10, de);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(igp));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", firstPrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), addresses);

    TrafficLabelStack stack = TrafficLabelStack.nodes("e", "f");
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, stack, SymbolicTrafficFraction.one());
    assertThat(matrix.get(de, stack).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(de, TrafficLabelStack.empty()).isZero(), equalTo(true));
  }

  @Test
  public void testForwardIpLongerPrefixWins() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    ForwardingRule def =
        ForwardingRule.direct(Prefix.parse("0.0.0.0/0"), GUARDS.trueGuard(), 10, ac);
    ForwardingRule exact = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", java.util.Arrays.asList(def, exact));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(ac, TrafficLabelStack.empty()).isZero(), equalTo(true));
  }

  @Test
  public void testForwardIpTwoWayDirectEcmp() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    ForwardingRule r1 = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab);
    ForwardingRule r2 = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ac);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", java.util.Arrays.asList(r1, r2));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(ab, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));
    assertThat(
        matrix.get(ac, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));
  }

  @Test
  public void testForwardIpUsesBackupWhenPreferredIsDown() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    ForwardingRule high = ForwardingRule.direct(DEST, GUARDS.variable("g_high"), 10, ab);
    ForwardingRule low = ForwardingRule.direct(DEST, GUARDS.variable("g_low"), 20, ac);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", java.util.Arrays.asList(high, low));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    Map<String, Boolean> preferredDown = new HashMap<>();
    preferredDown.put("g_high", false);
    preferredDown.put("g_low", true);
    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(ab, TrafficLabelStack.empty()).evaluate(preferredDown), closeTo(0.0, 1e-9));
    assertThat(
        matrix.get(ac, TrafficLabelStack.empty()).evaluate(preferredDown), closeTo(1.0, 1e-9));
  }

  @Test
  public void testForwardWithZeroOmegaIsEmpty() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraph g = graph(f, ab);
    ForwardingRule rule = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", Collections.singletonList(rule));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.zero());
    assertThat(matrix.isZero(), equalTo(true));
  }

  @Test
  public void testResolveNhIpMismatchedSrPolicyUsesVigp() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix nipPrefix = Prefix.parse("10.0.0.7/32");
    Ip otherNip = nipPrefix.getStartIp();
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, otherNip);
    ForwardingRule igp = ForwardingRule.direct(nipPrefix, GUARDS.trueGuard(), 10, de);
    SrPolicy.Path path =
        new SrPolicy.Path(GUARDS.trueGuard(), 1, java.util.Arrays.asList("e", "f"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", Ip.parse("10.0.0.5"));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(de, path.toStack()).isZero(), equalTo(true));
  }

  @Test
  public void testResolveNhIpTwoPathsDifferentStacks() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraphEdge dc = edge("d_c", "d", "c");
    TrafficGraph g = graph(f, de, dc);
    Prefix ePrefix = Prefix.parse("10.0.0.5/32");
    Prefix cPrefix = Prefix.parse("10.0.0.3/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igpE = ForwardingRule.direct(ePrefix, GUARDS.trueGuard(), 10, de);
    ForwardingRule igpC = ForwardingRule.direct(cPrefix, GUARDS.trueGuard(), 10, dc);
    SrPolicy.Path p1 =
        new SrPolicy.Path(GUARDS.trueGuard(), 75, java.util.Arrays.asList("e", "f"));
    SrPolicy.Path p2 =
        new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("c"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, java.util.Arrays.asList(p1, p2));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igpE, igpC));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", ePrefix.getStartIp());
    addresses.put("c", cPrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(matrix.get(de, p1.toStack()).evaluate(new HashMap<>()), closeTo(0.75, 1e-9));
    assertThat(matrix.get(dc, p2.toStack()).evaluate(new HashMap<>()), closeTo(0.25, 1e-9));
  }

  @Test
  public void testResolveNhIpTwoPathsSameStackSum() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix ePrefix = Prefix.parse("10.0.0.5/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igp = ForwardingRule.direct(ePrefix, GUARDS.trueGuard(), 10, de);
    SrPolicy.Path p1 =
        new SrPolicy.Path(GUARDS.trueGuard(), 75, Collections.singletonList("e"));
    SrPolicy.Path p2 =
        new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("e"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, java.util.Arrays.asList(p1, p2));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", ePrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(matrix.get(de, p1.toStack()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testForwardSrPopsThenKeepsRemainderTowardNextLabel() {
    TrafficFlow f = flow("e");
    TrafficGraphEdge ef = edge("e_f", "e", "f");
    TrafficGraph g = graph(f, ef);
    Prefix fPrefix = Prefix.parse("10.0.0.6/32");
    ForwardingRule igp = ForwardingRule.direct(fPrefix, GUARDS.trueGuard(), 10, ef);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("e", Collections.singletonList(igp));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("f", fPrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), addresses);

    TrafficLabelStack stack = TrafficLabelStack.nodes("e", "f");
    TrafficLabelStack remainder = TrafficLabelStack.nodes("f");
    SymbolicTrafficMatrix matrix =
        forwarding.forward("e", f, stack, SymbolicTrafficFraction.one());
    assertThat(matrix.get(ef, remainder).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(ef, TrafficLabelStack.empty()).isZero(), equalTo(true));
    assertThat(matrix.get(ef, stack).isZero(), equalTo(true));
  }

  @Test
  public void testResolveNhIpSkipsPathWithoutFirstNodeAddress() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(bgp));
    SrPolicy.Path path =
        new SrPolicy.Path(GUARDS.trueGuard(), 1, java.util.Arrays.asList("e", "f"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());

    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(matrix.isZero(), equalTo(true));
  }

  @Test
  public void testForwardIpConservesMassOnEcmp() {
    TrafficFlow f = flow("a");
    TrafficGraphEdge ab = edge("a_b", "a", "b");
    TrafficGraphEdge ac = edge("a_c", "a", "c");
    TrafficGraph g = graph(f, ab, ac);
    ForwardingRule r1 = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ab);
    ForwardingRule r2 = ForwardingRule.direct(DEST, GUARDS.trueGuard(), 10, ac);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("a", java.util.Arrays.asList(r1, r2));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, Collections.emptyMap(), Collections.emptyMap());
    SymbolicTrafficMatrix matrix =
        forwarding.forward("a", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(mass(matrix, new HashMap<String, Boolean>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testSrWeightedPathsConserveMass() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraphEdge dc = edge("d_c", "d", "c");
    TrafficGraph g = graph(f, de, dc);
    Prefix ePrefix = Prefix.parse("10.0.0.5/32");
    Prefix cPrefix = Prefix.parse("10.0.0.3/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igpE = ForwardingRule.direct(ePrefix, GUARDS.trueGuard(), 10, de);
    ForwardingRule igpC = ForwardingRule.direct(cPrefix, GUARDS.trueGuard(), 10, dc);
    SrPolicy.Path p1 =
        new SrPolicy.Path(GUARDS.trueGuard(), 75, java.util.Arrays.asList("e", "f"));
    SrPolicy.Path p2 =
        new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("c"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, java.util.Arrays.asList(p1, p2));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igpE, igpC));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", ePrefix.getStartIp());
    addresses.put("c", cPrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(mass(matrix, new HashMap<String, Boolean>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testPathGuardDoesNotReplaceIgpForwardingGuard() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraphEdge dc = edge("d_c", "d", "c");
    TrafficGraph g = graph(f, de, dc);
    Prefix ePrefix = Prefix.parse("10.0.0.5/32");
    Prefix cPrefix = Prefix.parse("10.0.0.3/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igpE =
        ForwardingRule.direct(ePrefix, GUARDS.variable("igp_e"), 10, de);
    ForwardingRule igpC = ForwardingRule.direct(cPrefix, GUARDS.trueGuard(), 10, dc);
    SrPolicy.Path p1 =
        new SrPolicy.Path(GUARDS.variable("path_e"), 75, Collections.singletonList("e"));
    SrPolicy.Path p2 =
        new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("c"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, java.util.Arrays.asList(p1, p2));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igpE, igpC));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", ePrefix.getStartIp());
    addresses.put("c", cPrefix.getStartIp());
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());

    Map<String, Boolean> pathUpIgpDown = new HashMap<>();
    pathUpIgpDown.put("path_e", true);
    pathUpIgpDown.put("igp_e", false);
    assertThat(matrix.get(de, p1.toStack()).evaluate(pathUpIgpDown), closeTo(0.0, 1e-9));
    assertThat(matrix.get(dc, p2.toStack()).evaluate(pathUpIgpDown), closeTo(0.25, 1e-9));
    assertThat(mass(matrix, pathUpIgpDown), closeTo(0.25, 1e-9));
  }

  @Test
  public void testHeadendOnlyStackPopsToIpForwarding() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix nipPrefix = Prefix.parse("10.0.0.6/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igp = ForwardingRule.direct(nipPrefix, GUARDS.trueGuard(), 10, de);
    SrPolicy.Path path =
        new SrPolicy.Path(GUARDS.trueGuard(), 1, Collections.singletonList("d"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(mass(matrix, new HashMap<String, Boolean>()), closeTo(1.0, 1e-9));
  }

  @Test
  public void testAdjSidRequiresSourceEqualCurrentRouter() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    SrPolicy.Path ok =
        new SrPolicy.Path(
            "ok",
            GUARDS.trueGuard(),
            1,
            Collections.singletonList(SrPolicy.Segment.adjacency("d", "e")));
    SrPolicy.Path wrongSource =
        new SrPolicy.Path(
            "bad",
            GUARDS.trueGuard(),
            1,
            Collections.singletonList(SrPolicy.Segment.adjacency("c", "x")));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, java.util.Arrays.asList(ok, wrongSource));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(bgp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(0.5, 1e-9));
    assertThat(matrix.get(de, ok.toStack()).isZero(), equalTo(true));
    assertThat(matrix.get(de, wrongSource.toStack()).isZero(), equalTo(true));
    assertThat(mass(matrix, new HashMap<String, Boolean>()), closeTo(0.5, 1e-9));
  }

  @Test
  public void testSecondAdjSidStaysTypedAndPopsOntoAdjacency() {
    TrafficFlow f = flow("e");
    TrafficGraphEdge ef = edge("e_f", "e", "f");
    TrafficGraph g = graph(f, ef);
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(
            g, Collections.emptyMap(), Collections.emptyMap(), Collections.emptyMap());
    TrafficLabelStack stack =
        new TrafficLabelStack(
            java.util.Arrays.asList(
                SrPolicy.Segment.adjacency("e", "f"), SrPolicy.Segment.node("x")));
    TrafficLabelStack remainder =
        new TrafficLabelStack(Collections.singletonList(SrPolicy.Segment.node("x")));
    SymbolicTrafficMatrix matrix =
        forwarding.forward("e", f, stack, SymbolicTrafficFraction.one());
    assertThat(matrix.get(ef, remainder).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(ef, TrafficLabelStack.nodes("f", "x")).isZero(), equalTo(true));
  }

  @Test
  public void testAdjSidAvailabilityGuardIsApplied() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    SrPolicy.Path path =
        new SrPolicy.Path(
            "ok",
            GUARDS.trueGuard(),
            1,
            Collections.singletonList(
                SrPolicy.Segment.adjacency("d", "e", GUARDS.variable("adj"))));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(bgp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    Map<String, Boolean> down = new HashMap<>();
    down.put("adj", false);
    assertThat(matrix.get(de, TrafficLabelStack.empty()).evaluate(down), closeTo(0.0, 1e-9));
    Map<String, Boolean> up = new HashMap<>();
    up.put("adj", true);
    assertThat(matrix.get(de, TrafficLabelStack.empty()).evaluate(up), closeTo(1.0, 1e-9));
  }

  @Test
  public void testAdjSidDoesNotInheritRibDirectAvailability() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    SrPolicy.Path path =
        new SrPolicy.Path(
            "ok",
            GUARDS.trueGuard(),
            1,
            Collections.singletonList(SrPolicy.Segment.adjacency("d", "e")));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    ForwardingRule directToE =
        ForwardingRule.direct(
            Prefix.parse("10.0.0.6/32"), GUARDS.variable("igp_down"), 10, de);
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, directToE));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());

    Map<String, Boolean> directDown = new HashMap<>();
    directDown.put("igp_down", false);
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(directDown), closeTo(1.0, 1e-9));
  }

  @Test
  public void testPolicyColorMismatchDoesNotApplySr() {
    TrafficFlow f =
        new TrafficFlow("d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.IP, null, null);
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    Prefix nipPrefix = Prefix.parse("10.0.0.6/32");
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    ForwardingRule igp = ForwardingRule.direct(nipPrefix, GUARDS.trueGuard(), 10, de);
    SrPolicy.Path path =
        new SrPolicy.Path(GUARDS.trueGuard(), 1, java.util.Arrays.asList("e", "f"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", java.util.Arrays.asList(bgp, igp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", Collections.singletonList(policy));
    Map<String, Ip> addresses = new HashMap<>();
    addresses.put("e", Ip.parse("10.0.0.5"));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, addresses);
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
    assertThat(
        matrix.get(de, TrafficLabelStack.empty()).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(de, path.toStack()).isZero(), equalTo(true));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testAmbiguousPoliciesAtSameSpecificityThrow() {
    TrafficFlow f =
        new TrafficFlow(
            "d-sr", "d", DEST, 80.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    TrafficGraphEdge de = edge("d_e", "d", "e");
    TrafficGraph g = graph(f, de);
    ForwardingRule bgp = ForwardingRule.indirect(DEST, GUARDS.trueGuard(), 10, NIP);
    SrPolicy.Path path = new SrPolicy.Path(GUARDS.trueGuard(), 1, Collections.singletonList("e"));
    SrPolicy p1 = new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    SrPolicy p2 =
        new SrPolicy("d", DEST, 100, "split-to-D", NIP, Collections.singletonList(path));
    Map<String, List<ForwardingRule>> ribs = new HashMap<>();
    ribs.put("d", Collections.singletonList(bgp));
    Map<String, List<SrPolicy>> policies = new HashMap<>();
    policies.put("d", java.util.Arrays.asList(p1, p2));
    SymbolicTrafficForwarding forwarding =
        new SymbolicTrafficForwarding(g, ribs, policies, Collections.emptyMap());
    forwarding.forward("d", f, TrafficLabelStack.empty(), SymbolicTrafficFraction.one());
  }

  private static double mass(SymbolicTrafficMatrix matrix, Map<String, Boolean> assignment) {
    double sum = 0.0;
    for (TrafficGraphEdge edge : matrix.edges()) {
      for (TrafficLabelStack stack : matrix.stacks()) {
        sum += matrix.get(edge, stack).evaluate(assignment);
      }
    }
    return sum;
  }
}
