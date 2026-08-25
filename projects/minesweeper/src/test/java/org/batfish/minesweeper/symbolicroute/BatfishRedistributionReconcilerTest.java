package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.RoutingProtocol.STATIC;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.util.Collections;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests policy-result reconciliation with symbolic contribution lifecycle operations. */
@RunWith(JUnit4.class)
public final class BatfishRedistributionReconcilerTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  private static StaticRoute route(long metric) {
    return StaticRoute.testBuilder()
        .setNetwork(Prefix.parse("192.0.2.0/24"))
        .setMetric(metric)
        .build();
  }

  private static BatfishRedistributionKey key() {
    return new BatfishRedistributionKey(
        "source-message", "r1", "source", "target", STATIC, STATIC, "export-policy");
  }

  private static SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network() {
    return SymbolicRouteNetworkFactory.create(
        ImmutableList.of("r1"),
        Collections.emptyList(),
        Collections.emptyList(),
        new BatfishMainRibRouteAdapter());
  }

  @Test
  public void testGuardUpdateKeepsContributionIdentity() {
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network = network();
    BatfishRedistributionReconciler reconciler = new BatfishRedistributionReconciler(network);
    BatfishRedistributionKey key = key();
    RouteGuard firstGuard = GUARDS.variable("first_guard");
    RouteGuard secondGuard = GUARDS.variable("second_guard");
    BatfishRoutingPolicyResult<StaticRoute> accepted =
        BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(10L), "target"));

    reconciler.reconcile(key, accepted, firstGuard);
    SymbolicRouteContributionId first = reconciler.getInstalledContributionId(key).get();
    reconciler.reconcile(key, accepted, secondGuard);

    assertThat(reconciler.getInstalledContributionId(key).get(), equalTo(first));
    assertThat(network.getRib("r1").getEntries(), hasSize(1));
    assertThat(
        network.getRib("r1").getEntries().get(0).getAvailabilityGuard().isEquivalentTo(secondGuard),
        equalTo(true));
  }

  @Test
  public void testTransformedRouteUsesAtomicReplacementAndNewIdentity() {
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network = network();
    BatfishRedistributionReconciler reconciler = new BatfishRedistributionReconciler(network);
    BatfishRedistributionKey key = key();
    reconciler.reconcile(
        key,
        BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(10L), "target")),
        GUARDS.trueGuard());
    SymbolicRouteContributionId old = reconciler.getInstalledContributionId(key).get();

    SymbolicRouteConvergenceResult replacement =
        reconciler.reconcile(
            key,
            BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(20L), "target")),
            GUARDS.trueGuard());

    assertThat(reconciler.getInstalledContributionId(key).get().equals(old), equalTo(false));
    assertThat(replacement.getProcessedWithdrawals() > 0, equalTo(true));
    assertThat(network.getRib("r1").getEntries(), hasSize(1));
    assertThat(
        network
            .getRib("r1")
            .getEntries()
            .get(0)
            .getSymbolicRoute()
            .getRoute()
            .getAbstractRoute()
            .getMetric(),
        equalTo(20L));
  }

  @Test
  public void testDenyWithdrawsPreviouslyAcceptedContribution() {
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network = network();
    BatfishRedistributionReconciler reconciler = new BatfishRedistributionReconciler(network);
    BatfishRedistributionKey key = key();
    reconciler.reconcile(
        key,
        BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(10L), "target")),
        GUARDS.trueGuard());

    SymbolicRouteConvergenceResult denied =
        reconciler.reconcile(key, BatfishRoutingPolicyResult.denied(), GUARDS.trueGuard());

    assertThat(denied.getProcessedWithdrawals() > 0, equalTo(true));
    assertThat(reconciler.getInstalledContributionId(key).isPresent(), equalTo(false));
    assertThat(network.getRib("r1").getEntries().isEmpty(), equalTo(true));
  }

  @Test
  public void testWrongTargetVrfIsRejectedWithoutReplacingInstalledRoute() {
    SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network = network();
    BatfishRedistributionReconciler reconciler = new BatfishRedistributionReconciler(network);
    BatfishRedistributionKey key = key();
    BatfishRoutingPolicyResult<StaticRoute> original =
        BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(10L), "target"));
    reconciler.reconcile(key, original, GUARDS.trueGuard());
    SymbolicRouteContributionId installed = reconciler.getInstalledContributionId(key).get();

    assertThrows(
        IllegalArgumentException.class,
        () ->
            reconciler.reconcile(
                key,
                BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(route(20L), "wrong-vrf")),
                GUARDS.trueGuard()));

    assertThat(reconciler.getInstalledContributionId(key).get(), equalTo(installed));
    assertThat(
        network
            .getRib("r1")
            .getEntries()
            .get(0)
            .getSymbolicRoute()
            .getRoute()
            .getAbstractRoute()
            .getMetric(),
        equalTo(10L));
  }

  private static void assertThrows(Class<? extends Throwable> expected, Runnable action) {
    try {
      action.run();
      throw new AssertionError("Expected " + expected.getSimpleName());
    } catch (Throwable thrown) {
      if (!expected.isInstance(thrown)) {
        throw new AssertionError(
            "Expected " + expected.getSimpleName() + " but caught " + thrown, thrown);
      }
    }
  }
}
