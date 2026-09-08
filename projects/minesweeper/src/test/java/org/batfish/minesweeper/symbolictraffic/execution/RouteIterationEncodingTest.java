package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
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
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** YU route-iteration encoding {@code VIGP} and {@code VSR}. */
@RunWith(JUnit4.class)
public class RouteIterationEncodingTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Ip NIP = Ip.parse("10.0.0.5");
  private static final Prefix NIP_PREFIX = Prefix.create(NIP, 32);

  private static TrafficGraphEdge edge(String id, String from, String to) {
    return new TrafficGraphEdge(id, from, to, "Ethernet0", "Ethernet0", 95.0, false);
  }

  @Test
  public void testVigpSumsEcmpShareOnEachDirectLink() {
    TrafficGraphEdge l1 = edge("d_e", "d", "e");
    TrafficGraphEdge l2 = edge("d_c", "d", "c");
    ForwardingRule r1 = ForwardingRule.direct(NIP_PREFIX, GUARDS.variable("y"), 10, l1);
    ForwardingRule r2 = ForwardingRule.direct(NIP_PREFIX, GUARDS.trueGuard(), 10, l2);
    List<ForwardingRule> rib = Arrays.asList(r1, r2);

    Map<String, Boolean> yUp = new HashMap<>();
    yUp.put("y", true);
    assertThat(RouteIterationEncoding.vigp(rib, NIP).get(l1).evaluate(yUp), closeTo(0.5, 1e-9));
    assertThat(RouteIterationEncoding.vigp(rib, NIP).get(l2).evaluate(yUp), closeTo(0.5, 1e-9));

    Map<String, Boolean> yDown = new HashMap<>();
    yDown.put("y", false);
    assertThat(RouteIterationEncoding.vigp(rib, NIP).get(l1).evaluate(yDown), closeTo(0.0, 1e-9));
    assertThat(RouteIterationEncoding.vigp(rib, NIP).get(l2).evaluate(yDown), closeTo(1.0, 1e-9));
  }

  @Test
  public void testVsrScalesIgpVectorByWeightedPathShare() {
    TrafficGraphEdge l1 = edge("d_e", "d", "e");
    ForwardingRule igp = ForwardingRule.direct(NIP_PREFIX, GUARDS.trueGuard(), 10, l1);
    SrPolicy.Path p1 =
        new SrPolicy.Path(GUARDS.trueGuard(), 75, Collections.singletonList("e"));
    SrPolicy.Path p2 =
        new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("c"));
    List<SrPolicy.Path> paths = Arrays.asList(p1, p2);

    assertThat(
        RouteIterationEncoding.pathShare(p1, paths).evaluate(new HashMap<>()),
        closeTo(0.75, 1e-9));
    assertThat(
        RouteIterationEncoding.vsr(p1, paths, Collections.singletonList(igp), NIP)
            .get(l1)
            .evaluate(new HashMap<>()),
        closeTo(0.75, 1e-9));
  }
}
