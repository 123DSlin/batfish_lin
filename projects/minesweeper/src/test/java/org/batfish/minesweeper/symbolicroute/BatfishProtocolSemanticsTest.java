package org.batfish.minesweeper.symbolicroute;

import static org.batfish.dataplane.protocols.StaticRouteHelper.shouldActivateNextHopIpRoute;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Solver;
import com.microsoft.z3.Status;
import java.util.Collections;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.batfish.dataplane.rib.Rib;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Differential tests for the symbolic lift of Batfish's concrete protocol semantics. */
@RunWith(JUnit4.class)
public final class BatfishProtocolSemanticsTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final String ROUTER = "r1";
  private static final String VRF = "default";

  private static AnnotatedRoute<AbstractRoute> annotate(AbstractRoute route) {
    return new AnnotatedRoute<>(route, VRF);
  }

  private static StaticRoute staticRoute(String network, String nextHopIp) {
    return StaticRoute.builder()
        .setNetwork(Prefix.parse(network))
        .setNextHopIp(org.batfish.datamodel.Ip.parse(nextHopIp))
        .setAdministrativeCost(1)
        .build();
  }

  private static void put(
      GuardedRib<AnnotatedRoute<AbstractRoute>> rib,
      String id,
      AnnotatedRoute<AbstractRoute> route,
      RouteGuard guard) {
    SymbolicRouteProvenance provenance =
        new SymbolicRouteProvenance(ROUTER, ROUTER, null, null, ImmutableList.of(ROUTER), null);
    SymbolicRoute<AnnotatedRoute<AbstractRoute>> symbolic =
        new SymbolicRoute<>(new SymbolicRouteKey(ROUTER, VRF, route), route, guard, provenance);
    rib.putContribution(new SymbolicRouteContributionId(id, ROUTER, ROUTER), symbolic);
  }

  private static boolean evaluate(
      RouteGuard guard, RouteGuard left, boolean leftValue, RouteGuard right, boolean rightValue) {
    Solver solver = CONTEXT.mkSolver();
    solver.add(((Z3RouteGuard) guard).getExpression());
    solver.add(value((Z3RouteGuard) left, leftValue));
    solver.add(value((Z3RouteGuard) right, rightValue));
    return solver.check() == Status.SATISFIABLE;
  }

  private static BoolExpr value(Z3RouteGuard guard, boolean value) {
    return value ? guard.getExpression() : CONTEXT.mkNot(guard.getExpression());
  }

  private static void assertThrows(Class<? extends Throwable> expected, Runnable action) {
    try {
      action.run();
      fail("Expected " + expected.getSimpleName());
    } catch (Throwable thrown) {
      if (!expected.isInstance(thrown)) {
        throw new AssertionError(
            "Expected " + expected.getSimpleName() + " but caught " + thrown, thrown);
      }
    }
  }

  @Test
  public void testMainRibPreferenceExactlyDelegatesToBatfishRib() {
    BatfishMainRibRouteAdapter adapter = new BatfishMainRibRouteAdapter();
    AnnotatedRoute<AbstractRoute> connected =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet0"));
    AnnotatedRoute<AbstractRoute> statik =
        annotate(
            StaticRoute.builder()
                .setNetwork(Prefix.parse("10.0.0.0/24"))
                .setNextHop(NextHopDiscard.instance())
                .setAdministrativeCost(1)
                .build());
    Rib concrete = new Rib();

    assertThat(
        Integer.signum(adapter.preferenceComparator(ROUTER).compare(connected, statik)),
        equalTo(-Integer.signum(concrete.comparePreference(connected, statik))));
  }

  @Test
  public void testSymbolicLpmMatchesConcreteBatfishForEveryGuardValuation() {
    RouteGuard broadGuard = GUARDS.variable("broad");
    RouteGuard specificGuard = GUARDS.variable("specific");
    AnnotatedRoute<AbstractRoute> broad =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/8"), "Ethernet0"));
    AnnotatedRoute<AbstractRoute> specific =
        annotate(new ConnectedRoute(Prefix.parse("10.1.0.0/16"), "Ethernet1"));
    StaticRoute target = staticRoute("192.0.2.0/24", "10.1.2.3");
    GuardedRib<AnnotatedRoute<AbstractRoute>> symbolicRib =
        new GuardedRib<>(new BatfishMainRibRouteAdapter().preferenceComparator(ROUTER));
    put(symbolicRib, "broad", broad, broadGuard);
    put(symbolicRib, "specific", specific, specificGuard);
    RouteGuard activation =
        BatfishStaticRouteResolver.activationGuard(
            symbolicRib,
            new SymbolicStaticRoute(
                "target", ROUTER, new AnnotatedRoute<>(target, VRF), GUARDS.trueGuard()));

    for (boolean broadPresent : ImmutableList.of(false, true)) {
      for (boolean specificPresent : ImmutableList.of(false, true)) {
        Rib concrete = new Rib();
        if (broadPresent) {
          concrete.mergeRoute(broad);
        }
        if (specificPresent) {
          concrete.mergeRoute(specific);
        }
        assertThat(
            evaluate(activation, broadGuard, broadPresent, specificGuard, specificPresent),
            equalTo(shouldActivateNextHopIpRoute(target, concrete)));
      }
    }
  }

  @Test
  public void testNonActivatingLongerPrefixStillBlocksShorterPrefix() {
    RouteGuard broadGuard = GUARDS.variable("blocking_broad");
    RouteGuard blockerGuard = GUARDS.variable("blocking_specific");
    AnnotatedRoute<AbstractRoute> broad =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/8"), "Ethernet0"));
    AnnotatedRoute<AbstractRoute> blocker = annotate(staticRoute("10.1.0.0/16", "203.0.113.1"));
    StaticRoute target = staticRoute("10.1.0.0/16", "10.1.2.3");
    GuardedRib<AnnotatedRoute<AbstractRoute>> symbolicRib =
        new GuardedRib<>(new BatfishMainRibRouteAdapter().preferenceComparator(ROUTER));
    put(symbolicRib, "blocking-broad", broad, broadGuard);
    put(symbolicRib, "blocking-specific", blocker, blockerGuard);
    RouteGuard activation =
        BatfishStaticRouteResolver.activationGuard(
            symbolicRib,
            new SymbolicStaticRoute(
                "blocking-target", ROUTER, new AnnotatedRoute<>(target, VRF), GUARDS.trueGuard()));

    for (boolean broadPresent : ImmutableList.of(false, true)) {
      for (boolean blockerPresent : ImmutableList.of(false, true)) {
        Rib concrete = new Rib();
        if (broadPresent) {
          concrete.mergeRoute(broad);
        }
        if (blockerPresent) {
          concrete.mergeRoute(blocker);
        }
        assertThat(
            evaluate(activation, broadGuard, broadPresent, blockerGuard, blockerPresent),
            equalTo(shouldActivateNextHopIpRoute(target, concrete)));
      }
    }
  }

  @Test
  public void testRecursiveStaticResolutionReachesFixedPoint() {
    RouteGuard connectedGuard = GUARDS.variable("connected");
    AnnotatedRoute<AbstractRoute> connected =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet0"));
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of(ROUTER),
            Collections.emptyList(),
            ImmutableList.of(
                new SymbolicRouteSeed<>("connected", ROUTER, connected, connectedGuard)),
            new BatfishMainRibRouteAdapter());
    network.converge();
    SymbolicStaticRoute first =
        new SymbolicStaticRoute(
            "first",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("20.0.0.0/24", "10.0.0.1"), VRF),
            GUARDS.trueGuard());
    SymbolicStaticRoute second =
        new SymbolicStaticRoute(
            "second",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("30.0.0.0/24", "20.0.0.1"), VRF),
            GUARDS.trueGuard());

    java.util.Map<SymbolicStaticRoute, RouteGuard> result =
        BatfishStaticRouteResolver.resolveToFixedPoint(network, ImmutableList.of(second, first));

    assertThat(result.get(first).isEquivalentTo(connectedGuard), equalTo(true));
    assertThat(result.get(second).isEquivalentTo(connectedGuard), equalTo(true));
  }

  @Test
  public void testResolutionStartsWithoutStaleStaticContributions() {
    RouteGuard connectedGuard = GUARDS.variable("initial_connected");
    AnnotatedRoute<AbstractRoute> connected =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet0"));
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of(ROUTER),
            Collections.emptyList(),
            ImmutableList.of(
                new SymbolicRouteSeed<>("initial-connected", ROUTER, connected, connectedGuard)),
            new BatfishMainRibRouteAdapter());
    network.converge();
    SymbolicStaticRoute statik =
        new SymbolicStaticRoute(
            "stale",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("20.0.0.0/24", "10.0.0.1"), VRF),
            GUARDS.trueGuard());
    assertThat(
        BatfishStaticRouteResolver.resolveToFixedPoint(network, ImmutableList.of(statik))
            .get(statik)
            .isEquivalentTo(connectedGuard),
        equalTo(true));

    network
        .getEngine()
        .withdraw(
            ImmutableList.of(new SymbolicRouteContributionId("initial-connected", ROUTER, ROUTER)));
    RouteGuard recomputed =
        BatfishStaticRouteResolver.resolveToFixedPoint(network, ImmutableList.of(statik))
            .get(statik);

    assertThat(recomputed.isFalse(), equalTo(true));
  }

  @Test
  public void testSameUserMessageIdIsIsolatedByVrf() {
    RouteGuard blueGuard = GUARDS.variable("blue_connected");
    RouteGuard redGuard = GUARDS.variable("red_connected");
    AnnotatedRoute<AbstractRoute> blueConnected =
        new AnnotatedRoute<>(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet0"), "blue");
    AnnotatedRoute<AbstractRoute> redConnected =
        new AnnotatedRoute<>(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet1"), "red");
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of(ROUTER),
            Collections.emptyList(),
            ImmutableList.of(
                new SymbolicRouteSeed<>("blue-connected", ROUTER, blueConnected, blueGuard),
                new SymbolicRouteSeed<>("red-connected", ROUTER, redConnected, redGuard)),
            new BatfishMainRibRouteAdapter());
    network.converge();
    SymbolicStaticRoute blue =
        new SymbolicStaticRoute(
            "same-id",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("20.0.0.0/24", "10.0.0.1"), "blue"),
            GUARDS.trueGuard());
    SymbolicStaticRoute red =
        new SymbolicStaticRoute(
            "same-id",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("20.0.0.0/24", "10.0.0.1"), "red"),
            GUARDS.trueGuard());

    java.util.Map<SymbolicStaticRoute, RouteGuard> result =
        BatfishStaticRouteResolver.resolveToFixedPoint(network, ImmutableList.of(blue, red));

    assertThat(result.get(blue).isEquivalentTo(blueGuard), equalTo(true));
    assertThat(result.get(red).isEquivalentTo(redGuard), equalTo(true));
  }

  @Test
  public void testInvalidBatchDoesNotPartiallyInstallEarlierRoute() {
    AnnotatedRoute<AbstractRoute> connected =
        annotate(new ConnectedRoute(Prefix.parse("10.0.0.0/24"), "Ethernet0"));
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of(ROUTER),
            Collections.emptyList(),
            ImmutableList.of(
                new SymbolicRouteSeed<>("atomic-connected", ROUTER, connected, GUARDS.trueGuard())),
            new BatfishMainRibRouteAdapter());
    network.converge();
    SymbolicStaticRoute valid =
        new SymbolicStaticRoute(
            "valid",
            ROUTER,
            new AnnotatedRoute<>(staticRoute("20.0.0.0/24", "10.0.0.1"), VRF),
            GUARDS.trueGuard());
    StaticRoute invalidRoute =
        StaticRoute.builder()
            .setNetwork(Prefix.parse("30.0.0.0/24"))
            .setNextHop(NextHopDiscard.instance())
            .setAdministrativeCost(1)
            .build();
    SymbolicStaticRoute invalid =
        new SymbolicStaticRoute(
            "invalid", ROUTER, new AnnotatedRoute<>(invalidRoute, VRF), GUARDS.trueGuard());

    assertThrows(
        IllegalArgumentException.class,
        () ->
            BatfishStaticRouteResolver.resolveToFixedPoint(
                network, ImmutableList.of(valid, invalid)));

    assertThat(network.getRib(ROUTER).getEntries(), hasSize(1));
  }

  @Test
  public void testRejectsUnownedPreinstalledRecursiveCandidate() {
    StaticRoute concreteStatic = staticRoute("20.0.0.0/24", "10.0.0.1");
    AnnotatedRoute<AbstractRoute> preinstalled = annotate(concreteStatic);
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of(ROUTER),
            Collections.emptyList(),
            ImmutableList.of(
                new SymbolicRouteSeed<>(
                    "foreign-static", ROUTER, preinstalled, GUARDS.trueGuard())),
            new BatfishMainRibRouteAdapter());
    network.converge();
    SymbolicStaticRoute statik =
        new SymbolicStaticRoute(
            "owned-static", ROUTER, new AnnotatedRoute<>(concreteStatic, VRF), GUARDS.trueGuard());

    assertThrows(
        IllegalArgumentException.class,
        () -> BatfishStaticRouteResolver.resolveToFixedPoint(network, ImmutableList.of(statik)));

    assertThat(network.getRib(ROUTER).getEntries(), hasSize(1));
  }
}
