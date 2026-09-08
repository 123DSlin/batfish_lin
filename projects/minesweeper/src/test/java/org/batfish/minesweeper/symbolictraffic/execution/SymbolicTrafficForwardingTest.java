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

    TrafficLabelStack stack = new TrafficLabelStack(Collections.singletonList("e"));
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

    TrafficLabelStack stack = new TrafficLabelStack(java.util.Arrays.asList("e", "f"));
    SymbolicTrafficMatrix matrix =
        forwarding.forward("d", f, stack, SymbolicTrafficFraction.one());
    assertThat(matrix.get(de, stack).evaluate(new HashMap<>()), closeTo(1.0, 1e-9));
    assertThat(matrix.get(de, TrafficLabelStack.empty()).isZero(), equalTo(true));
  }
}
