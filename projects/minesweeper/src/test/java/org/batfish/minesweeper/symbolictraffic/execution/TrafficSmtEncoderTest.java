package org.batfish.minesweeper.symbolictraffic.execution;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import java.util.Arrays;
import java.util.Collections;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.AstRouteGuard;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficFlow;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraph;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

@RunWith(JUnit4.class)
public class TrafficSmtEncoderTest {

  @Test
  public void testEncodeAllUpDeclaresPinnedConfigWeights() {
    TrafficGraphEdge aS = new TrafficGraphEdge("a_s", "s", "a", "Gi0", "Gi0", 95.0, false);
    TrafficGraphEdge aD = new TrafficGraphEdge("a_d", "a", "d", "Gi0", "Gi0", 95.0, false);
    TrafficGraphEdge bS = new TrafficGraphEdge("b_s", "s", "b", "Gi0", "Gi0", 95.0, false);
    TrafficGraphEdge bD = new TrafficGraphEdge("b_d", "b", "d", "Gi0", "Gi0", 95.0, false);
    TrafficGraphEdge dX = new TrafficGraphEdge("d_x", "x", "d", "Gi0", "Gi0", 95.0, false);

    TrafficFlow sr =
        new TrafficFlow(
            "s-sr-to-d",
            "s",
            Prefix.parse("5.5.5.5/32"),
            80.0,
            TrafficFlow.ForwardingType.SR_POLICY,
            100,
            "split-to-D");
    TrafficFlow ip =
        new TrafficFlow(
            "x-ip-to-d",
            "x",
            Prefix.parse("5.5.5.5/32"),
            20.0,
            TrafficFlow.ForwardingType.IP,
            null,
            null);

    TrafficGraph graph =
        new TrafficGraph(
            Arrays.asList("s", "a", "b", "d", "x"),
            Arrays.asList(aS, aD, bS, bD, dX),
            Arrays.asList(sr, ip));

    String wa = "Config_s_SrPolicy_split_to_D_Path_upper_via_A_weight";
    String wb = "Config_s_SrPolicy_split_to_D_Path_lower_via_B_weight";
    SymbolicTrafficFraction weightA = SymbolicTrafficFraction.weight(wa, 50);
    SymbolicTrafficFraction weightB = SymbolicTrafficFraction.weight(wb, 50);
    SymbolicTrafficFraction srA = weightA.div(weightA.plus(weightB)).times(80.0);
    SymbolicTrafficFraction srB = weightB.div(weightA.plus(weightB)).times(80.0);
    SymbolicTrafficLoad yu = new SymbolicTrafficLoad();
    yu.add(aS, srA);
    yu.add(aD, srA);
    yu.add(bS, srB);
    yu.add(bD, srB);
    yu.add(dX, new SymbolicTrafficFraction(20.0));
    String smt = TrafficSmtEncoder.encodeSymbolic(graph, yu);
    assertThat(smt, containsString("(declare-fun " + wa));
    assertThat(smt, containsString("(assert (= " + wa + " 50))"));
    assertThat(smt, containsString("(assert (>= " + wa + " 1))"));
    assertThat(smt, containsString("(assert (<= " + wa + " 4294967295))"));
    assertThat(smt, containsString("(to_real " + wa + ")"));
    assertThat(smt, containsString("load_a_d_a_d"));
    assertThat(smt, containsString("(assert (= load_d_x_x_d 20.0))"));
    assertThat(smt, containsString("(assert (< load_a_d_a_d 95.0))"));
    assertThat(smt, containsString(";(get-model)"));
  }

  @Test
  public void testWeightConfigVarNaming() {
    assertThat(
        GuardedTrafficForwarding.weightConfigVar("s", "split-to-D", "upper-via-A"),
        equalTo("Config_s_SrPolicy_split_to_D_Path_upper_via_A_weight"));
  }

  @Test
  public void testPathSharePreservesConfigWeightsForYu() {
    SrPolicy.Path p1 =
        new SrPolicy.Path(
            "upper",
            AstRouteGuard.alwaysTrue(),
            50,
            "Config_s_SrPolicy_p_Path_upper_weight",
            Collections.singletonList(SrPolicy.Segment.node("a")));
    SrPolicy.Path p2 =
        new SrPolicy.Path(
            "lower",
            AstRouteGuard.alwaysTrue(),
            50,
            "Config_s_SrPolicy_p_Path_lower_weight",
            Collections.singletonList(SrPolicy.Segment.node("b")));
    SymbolicTrafficFraction share = RouteIterationEncoding.pathShare(p1, Arrays.asList(p1, p2));
    assertThat(share.evaluateAllUp(), closeTo(0.5, 1e-9));
    java.util.Map<String, Integer> weights = new java.util.TreeMap<>();
    share.collectWeights(weights);
    assertThat(weights.size(), equalTo(2));
    assertThat(weights.get("Config_s_SrPolicy_p_Path_upper_weight"), equalTo(50));
    assertThat(weights.get("Config_s_SrPolicy_p_Path_lower_weight"), equalTo(50));
  }
}
