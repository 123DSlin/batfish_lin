package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.util.Comparator;
import java.util.Optional;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of network-level symbolic route work-queue convergence. */
@RunWith(JUnit4.class)
public final class SymbolicRouteConvergenceEngineTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix NETWORK = Prefix.parse("10.0.0.0/24");
  private static final Comparator<StaticRoute> PREFERENCE =
      Comparator.comparingInt(StaticRoute::getAdministrativeCost);

  private static StaticRoute route(int administrativeCost) {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(administrativeCost)
        .build();
  }

  private static SymbolicRouteIngressProcessor<StaticRoute> processor(
      String router, GuardedRib<StaticRoute> rib) {
    return new SymbolicRouteIngressProcessor<>(
        router,
        rib,
        message -> Optional.of(message.getRoute()),
        (receiver, route) -> new SymbolicRouteKey(receiver, "default", route));
  }

  private static SymbolicRouteExporter<StaticRoute> exporter(
      String sender,
      String receiver,
      RouteGuard linkGuard,
      SymbolicRouteEgressPolicy<StaticRoute> policy,
      SymbolicRoutePropagationDependencies dependencies) {
    return new SymbolicRouteExporter<>(
        sender,
        receiver,
        linkGuard,
        policy,
        (from, to, route) -> from + "->" + to + ":" + route.getAdministrativeCost(),
        dependencies);
  }

  private static SymbolicRouteMessage<StaticRoute> initial(
      String receiver, StaticRoute route, RouteGuard guard) {
    return new SymbolicRouteMessage<>(
        "origin->" + receiver + ":" + route.getAdministrativeCost(),
        "origin",
        receiver,
        SymbolicRouteMessage.Stage.INGRESS,
        route,
        guard,
        new SymbolicRouteProvenance(
            "origin", receiver, "origin", null, ImmutableList.of("origin", receiver), null));
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
  public void testThreeRouterPropagationConvergesWithAccumulatedLinkGuards() {
    RouteGuard seed = GUARDS.variable("converge_seed");
    RouteGuard ab = GUARDS.variable("converge_ab");
    RouteGuard bc = GUARDS.variable("converge_bc");
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> c = new GuardedRib<>(PREFERENCE);
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b), processor("c", c)),
            ImmutableList.of(
                exporter("a", "b", ab, (s, r, candidate) -> Optional.of(candidate), dependencies),
                exporter("b", "c", bc, (s, r, candidate) -> Optional.of(candidate), dependencies)));

    SymbolicRouteConvergenceResult result =
        engine.converge(ImmutableList.of(initial("a", route, seed)));

    assertThat(result.getProcessedMessages(), equalTo(3));
    assertThat(a.getEntries(), hasSize(1));
    assertThat(b.getEntries(), hasSize(1));
    assertThat(c.getEntries(), hasSize(1));
    assertThat(
        c.get(new SymbolicRouteKey("c", "default", route))
            .getAvailabilityGuard()
            .isEquivalentTo(seed.and(ab).and(bc)),
        equalTo(true));
  }

  @Test
  public void testEquivalentReplayTerminatesWithoutPropagation() {
    StaticRoute route = route(10);
    RouteGuard seed = GUARDS.variable("replay_seed");
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    GUARDS.variable("replay_link"),
                    (s, r, candidate) -> Optional.of(candidate),
                    new SymbolicRoutePropagationDependencies())));

    engine.converge(ImmutableList.of(initial("a", route, seed)));
    SymbolicRouteConvergenceResult replay =
        engine.converge(ImmutableList.of(initial("a", route, seed)));

    assertThat(replay.getProcessedMessages(), equalTo(1));
    assertThat(replay.getRibUpdates(), equalTo(0));
  }

  @Test
  public void testEgressDenyStopsPropagation() {
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    GUARDS.variable("deny_link"),
                    (s, r, candidate) -> Optional.empty(),
                    new SymbolicRoutePropagationDependencies())));

    SymbolicRouteConvergenceResult result =
        engine.converge(ImmutableList.of(initial("a", route, GUARDS.variable("deny_seed"))));

    assertThat(result.getProcessedMessages(), equalTo(1));
    assertThat(b.getEntries().isEmpty(), equalTo(true));
  }

  @Test
  public void testRejectsUnknownReceiver() {
    StaticRoute route = route(10);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", new GuardedRib<>(PREFERENCE))), ImmutableList.of());

    assertThrows(
        IllegalArgumentException.class,
        () ->
            engine.converge(
                ImmutableList.of(initial("missing", route, GUARDS.variable("missing_receiver")))));
  }
}
