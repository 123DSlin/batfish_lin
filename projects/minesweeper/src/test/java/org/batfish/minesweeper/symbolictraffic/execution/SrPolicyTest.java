package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import java.util.Arrays;
import java.util.Collections;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Construction constraints on SR paths used by Algorithm 2. */
@RunWith(JUnit4.class)
public class SrPolicyTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix DEST = Prefix.parse("5.5.5.5/32");

  @Test(expected = IllegalArgumentException.class)
  public void testPathRejectsEmptySegments() {
    new SrPolicy.Path(GUARDS.trueGuard(), 1, Collections.emptyList());
  }

  @Test(expected = IllegalArgumentException.class)
  public void testPathRejectsNullSegment() {
    new SrPolicy.Path(
        null,
        GUARDS.trueGuard(),
        1,
        Collections.<SrPolicy.Segment>singletonList(null));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testPathRejectsNonPositiveWeight() {
    new SrPolicy.Path(GUARDS.trueGuard(), 0, Collections.singletonList("e"));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testNodeSidRejectsNullRouter() {
    SrPolicy.Segment.node(null);
  }

  @Test(expected = IllegalArgumentException.class)
  public void testAdjSidRejectsNullSource() {
    SrPolicy.Segment.adjacency(null, "e");
  }

  @Test(expected = IllegalArgumentException.class)
  public void testDuplicatePathIdsRejected() {
    SrPolicy.Path p1 =
        new SrPolicy.Path(
            "p", GUARDS.trueGuard(), 1, Collections.singletonList(SrPolicy.Segment.node("e")));
    SrPolicy.Path p2 =
        new SrPolicy.Path(
            "p", GUARDS.trueGuard(), 1, Collections.singletonList(SrPolicy.Segment.node("c")));
    new SrPolicy("d", DEST, 100, "split-to-D", null, Arrays.asList(p1, p2));
  }

  @Test
  public void testDuplicateStacksAreAllowed() {
    SrPolicy.Path p1 = new SrPolicy.Path(GUARDS.trueGuard(), 75, Collections.singletonList("e"));
    SrPolicy.Path p2 = new SrPolicy.Path(GUARDS.trueGuard(), 25, Collections.singletonList("e"));
    SrPolicy policy = new SrPolicy("d", DEST, 100, "split-to-D", null, Arrays.asList(p1, p2));
    assertThat(policy.getPaths().size(), equalTo(2));
  }

  @Test
  public void testHeadendOnlyNodeListIsAllowed() {
    SrPolicy.Path path = new SrPolicy.Path(GUARDS.trueGuard(), 1, Collections.singletonList("d"));
    assertThat(path.getFirstSegment().getRouter(), equalTo("d"));
    assertThat(
        path.toStack().getSegments(),
        equalTo(Collections.singletonList(SrPolicy.Segment.node("d"))));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testLabelStackRejectsNullSegment() {
    new TrafficLabelStack(Collections.singletonList(null));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testPolicyRejectsEmptyPathList() {
    new SrPolicy("d", DEST, 100, "split-to-D", null, Collections.emptyList());
  }

  @Test
  public void testColorRequiredWhenPolicySetsColor() {
    SrPolicy.Path path = new SrPolicy.Path(GUARDS.trueGuard(), 1, Collections.singletonList("e"));
    SrPolicy policy =
        new SrPolicy("d", DEST, 100, "split-to-D", null, Collections.singletonList(path));
    TrafficFlow noColor =
        new TrafficFlow(
            "f", "d", DEST, 1.0, TrafficFlow.ForwardingType.SR_POLICY, null, "split-to-D");
    TrafficFlow colored =
        new TrafficFlow(
            "f", "d", DEST, 1.0, TrafficFlow.ForwardingType.SR_POLICY, 100, "split-to-D");
    assertThat(policy.matches("d", noColor, null), equalTo(false));
    assertThat(policy.matches("d", colored, null), equalTo(true));
  }
}
