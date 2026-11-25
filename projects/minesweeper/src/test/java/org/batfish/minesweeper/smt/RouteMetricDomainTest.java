package org.batfish.minesweeper.smt;

import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.nullValue;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import java.util.List;
import org.batfish.minesweeper.Protocol;
import org.junit.Test;

public final class RouteMetricDomainTest {

  private static Status checkMetric(
      Protocol protocol, List<Protocol> protocols, boolean env, int value) {
    try (Context context = new Context()) {
      ArithExpr metric = context.mkIntConst("metric");
      Solver solver = context.mkSolver();
      solver.add(
          RouteMetricDomain.constraints(
              context, metric, RouteMetricDomain.exclusiveUpperBound(protocol, protocols, env)),
          context.mkEq(metric, context.mkInt(value)));
      return solver.check();
    }
  }

  @Test
  public void testBgpPathCanGrowBeyondLegacyMetricCap() {
    assertThat(
        checkMetric(Protocol.BGP, List.of(Protocol.BGP), false, 65538),
        equalTo(Status.SATISFIABLE));
  }

  @Test
  public void testBgpOnlyOverallBestUsesSamePathDomain() {
    assertThat(
        checkMetric(
            Protocol.BEST,
            List.of(Protocol.CONNECTED, Protocol.STATIC, Protocol.BGP),
            false,
            65538),
        equalTo(Status.SATISFIABLE));
  }

  @Test
  public void testNegativeBgpLengthRejected() {
    assertThat(
        checkMetric(Protocol.BGP, List.of(Protocol.BGP), false, -1), equalTo(Status.UNSATISFIABLE));
  }

  @Test
  public void testEnvironmentBoundPreserved() {
    assertThat(
        checkMetric(Protocol.BGP, List.of(Protocol.BGP), true, 255), equalTo(Status.SATISFIABLE));
    assertThat(
        checkMetric(Protocol.BGP, List.of(Protocol.BGP), true, 256), equalTo(Status.UNSATISFIABLE));
  }

  @Test
  public void testOspfBoundPreserved() {
    assertThat(
        checkMetric(Protocol.OSPF, List.of(Protocol.OSPF), false, 65535),
        equalTo(Status.SATISFIABLE));
    assertThat(
        checkMetric(Protocol.OSPF, List.of(Protocol.OSPF), false, 65536),
        equalTo(Status.UNSATISFIABLE));
  }

  @Test
  public void testMixedProtocolBestRetainsExistingDomain() {
    for (Protocol igp : List.of(Protocol.OSPF, Protocol.ISIS_L1, Protocol.ISIS_L2)) {
      assertThat(
          checkMetric(Protocol.BEST, List.of(Protocol.BGP, igp), false, 65536),
          equalTo(Status.UNSATISFIABLE));
    }
  }

  @Test
  public void testBestWithoutBgpRetainsExistingDomain() {
    assertThat(
        RouteMetricDomain.exclusiveUpperBound(Protocol.BEST, List.of(Protocol.CONNECTED), false),
        equalTo(65536L));
  }

  @Test
  public void testCopiesRetainDomain() {
    SymbolicRoute bgp = new SymbolicRoute("bgp", Protocol.BGP);
    assertThat(bgp.getMetricUpperBound(), nullValue());
    assertThat(bgp.copy().getMetricUpperBound(), nullValue());
    SymbolicRoute ospf = new SymbolicRoute("ospf", Protocol.OSPF);
    assertThat(ospf.copy().getMetricUpperBound(), equalTo(65536L));
  }
}
