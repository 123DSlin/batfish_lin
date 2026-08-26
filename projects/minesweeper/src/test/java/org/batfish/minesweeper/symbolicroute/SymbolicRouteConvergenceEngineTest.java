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
        (from, to, key, route) -> from + "->" + to + ":" + route.getAdministrativeCost(),
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

  @Test
  public void testLateHigherPriorityRouteRecursivelyReplacesLowerAdvertisements() {
    RouteGuard lowGuard = GUARDS.variable("late_low");
    RouteGuard highGuard = GUARDS.variable("late_high");
    RouteGuard ab = GUARDS.variable("late_ab");
    RouteGuard bc = GUARDS.variable("late_bc");
    StaticRoute low = route(20);
    StaticRoute high = route(10);
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

    engine.converge(ImmutableList.of(initial("a", low, lowGuard)));
    SymbolicRouteConvergenceResult lateHighResult =
        engine.converge(ImmutableList.of(initial("a", high, highGuard)));

    assertThat(lateHighResult.getProcessedWithdrawals() > 0, equalTo(true));
    assertThat(c.getEntries(), hasSize(2));
    assertThat(
        c.get(new SymbolicRouteKey("c", "default", high))
            .getAvailabilityGuard()
            .isEquivalentTo(highGuard.and(ab).and(bc)),
        equalTo(true));
    assertThat(
        c.get(new SymbolicRouteKey("c", "default", low))
            .getAvailabilityGuard()
            .isEquivalentTo(lowGuard.and(highGuard.not()).and(ab).and(bc)),
        equalTo(true));

    GuardedRib<StaticRoute> aHighFirst = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> bHighFirst = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> cHighFirst = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> highFirstEngine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(
                processor("a", aHighFirst), processor("b", bHighFirst), processor("c", cHighFirst)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    ab,
                    (s, r, candidate) -> Optional.of(candidate),
                    new SymbolicRoutePropagationDependencies()),
                exporter(
                    "b",
                    "c",
                    bc,
                    (s, r, candidate) -> Optional.of(candidate),
                    new SymbolicRoutePropagationDependencies())));
    highFirstEngine.converge(
        ImmutableList.of(initial("a", high, highGuard), initial("a", low, lowGuard)));

    assertThat(
        c.get(new SymbolicRouteKey("c", "default", low))
            .getAvailabilityGuard()
            .isEquivalentTo(
                cHighFirst.get(new SymbolicRouteKey("c", "default", low)).getAvailabilityGuard()),
        equalTo(true));
    assertThat(
        c.get(new SymbolicRouteKey("c", "default", high))
            .getAvailabilityGuard()
            .isEquivalentTo(
                cHighFirst.get(new SymbolicRouteKey("c", "default", high)).getAvailabilityGuard()),
        equalTo(true));
  }

  @Test
  public void testRootWithdrawalRecursivelyRemovesDescendants() {
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> c = new GuardedRib<>(PREFERENCE);
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b), processor("c", c)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    GUARDS.variable("withdraw_ab"),
                    (s, r, candidate) -> Optional.of(candidate),
                    dependencies),
                exporter(
                    "b",
                    "c",
                    GUARDS.variable("withdraw_bc"),
                    (s, r, candidate) -> Optional.of(candidate),
                    dependencies)));
    SymbolicRouteMessage<StaticRoute> seed = initial("a", route, GUARDS.variable("withdraw_seed"));
    engine.converge(ImmutableList.of(seed));

    SymbolicRouteContributionId root =
        new SymbolicRouteContributionId(seed.getMessageId(), seed.getSender(), seed.getReceiver());
    SymbolicRouteConvergenceResult result = engine.withdraw(ImmutableList.of(root));

    assertThat(result.getProcessedWithdrawals(), equalTo(3));
    assertThat(a.getEntries().isEmpty(), equalTo(true));
    assertThat(b.getEntries().isEmpty(), equalTo(true));
    assertThat(c.getEntries().isEmpty(), equalTo(true));
    assertThat(dependencies.getChildren(root).isEmpty(), equalTo(true));
  }

  @Test
  public void testWithdrawingOneOfTwoContributionsKeepsCandidateAndIsIdempotent() {
    StaticRoute route = route(10);
    RouteGuard leftGuard = GUARDS.variable("multi_left");
    RouteGuard rightGuard = GUARDS.variable("multi_right");
    RouteGuard link = GUARDS.variable("multi_link");
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    link,
                    (s, r, candidate) -> Optional.of(candidate),
                    new SymbolicRoutePropagationDependencies())));
    SymbolicRouteMessage<StaticRoute> left = initial("a", route, leftGuard);
    SymbolicRouteMessage<StaticRoute> right =
        new SymbolicRouteMessage<>(
            "second-origin->a:10",
            "second-origin",
            "a",
            SymbolicRouteMessage.Stage.INGRESS,
            route,
            rightGuard,
            new SymbolicRouteProvenance(
                "second-origin",
                "a",
                "second-origin",
                null,
                ImmutableList.of("second-origin", "a"),
                null));
    engine.converge(ImmutableList.of(left, right));
    SymbolicRouteContributionId leftId =
        new SymbolicRouteContributionId(left.getMessageId(), left.getSender(), left.getReceiver());

    engine.withdraw(ImmutableList.of(leftId));

    assertThat(a.getEntries(), hasSize(1));
    assertThat(b.getEntries(), hasSize(1));
    assertThat(
        a.get(new SymbolicRouteKey("a", "default", route))
            .getAvailabilityGuard()
            .isEquivalentTo(rightGuard),
        equalTo(true));
    assertThat(
        b.get(new SymbolicRouteKey("b", "default", route))
            .getAvailabilityGuard()
            .isEquivalentTo(rightGuard.and(link)),
        equalTo(true));
    SymbolicRouteConvergenceResult duplicate = engine.withdraw(ImmutableList.of(leftId));
    assertThat(duplicate.getProcessedWithdrawals(), equalTo(0));
    assertThat(duplicate.getRibUpdates(), equalTo(0));
  }

  @Test
  public void testRouteReplacementWithdrawsOldAndAddsNewIdentity() {
    StaticRoute oldRoute = route(20);
    StaticRoute newRoute = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> b = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a), processor("b", b)),
            ImmutableList.of(
                exporter(
                    "a",
                    "b",
                    GUARDS.variable("replacement_link"),
                    (s, r, candidate) -> Optional.of(candidate),
                    new SymbolicRoutePropagationDependencies())));
    SymbolicRouteMessage<StaticRoute> oldAdvertisement =
        initial("a", oldRoute, GUARDS.variable("replacement_old"));
    engine.converge(ImmutableList.of(oldAdvertisement));
    SymbolicRouteContributionId oldId =
        new SymbolicRouteContributionId(
            oldAdvertisement.getMessageId(),
            oldAdvertisement.getSender(),
            oldAdvertisement.getReceiver());
    SymbolicRouteMessage<StaticRoute> replacement =
        initial("a", newRoute, GUARDS.variable("replacement_new"));

    SymbolicRouteConvergenceResult result = engine.replace(oldId, replacement);

    assertThat(result.getProcessedWithdrawals() > 0, equalTo(true));
    assertThat(a.get(new SymbolicRouteKey("a", "default", oldRoute)) == null, equalTo(true));
    assertThat(b.get(new SymbolicRouteKey("b", "default", oldRoute)) == null, equalTo(true));
    assertThat(a.get(new SymbolicRouteKey("a", "default", newRoute)) == null, equalTo(false));
    assertThat(b.get(new SymbolicRouteKey("b", "default", newRoute)) == null, equalTo(false));
  }

  @Test
  public void testRouteReplacementRequiresNewContributionIdentity() {
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a)), ImmutableList.of());
    SymbolicRouteMessage<StaticRoute> advertisement =
        initial("a", route, GUARDS.variable("same_identity"));
    engine.converge(ImmutableList.of(advertisement));
    SymbolicRouteContributionId id =
        new SymbolicRouteContributionId(
            advertisement.getMessageId(), advertisement.getSender(), advertisement.getReceiver());

    assertThrows(IllegalArgumentException.class, () -> engine.replace(id, advertisement));
  }

  @Test
  public void testSameContributionCannotMoveCandidateAndDoesNotMutateRib() {
    StaticRoute oldRoute = route(20);
    StaticRoute changedRoute = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a)), ImmutableList.of());
    SymbolicRouteMessage<StaticRoute> original =
        initial("a", oldRoute, GUARDS.variable("identity_original"));
    engine.converge(ImmutableList.of(original));
    SymbolicRouteMessage<StaticRoute> illegalMove =
        new SymbolicRouteMessage<>(
            original.getMessageId(),
            original.getSender(),
            original.getReceiver(),
            original.getStage(),
            changedRoute,
            GUARDS.variable("identity_changed"),
            original.getProvenance());

    assertThrows(
        IllegalArgumentException.class, () -> engine.converge(ImmutableList.of(illegalMove)));

    assertThat(a.getEntries(), hasSize(1));
    assertThat(a.get(new SymbolicRouteKey("a", "default", oldRoute)) == null, equalTo(false));
    assertThat(a.get(new SymbolicRouteKey("a", "default", changedRoute)) == null, equalTo(true));
  }

  @Test
  public void testRouteReplacementRequiresExistingOldAndUnusedNewIdentity() {
    StaticRoute oldRoute = route(20);
    StaticRoute newRoute = route(10);
    GuardedRib<StaticRoute> a = new GuardedRib<>(PREFERENCE);
    SymbolicRouteConvergenceEngine<StaticRoute> engine =
        new SymbolicRouteConvergenceEngine<>(
            ImmutableList.of(processor("a", a)), ImmutableList.of());
    SymbolicRouteMessage<StaticRoute> oldAdvertisement =
        initial("a", oldRoute, GUARDS.variable("existing_old"));
    SymbolicRouteMessage<StaticRoute> alreadyUsed =
        initial("a", newRoute, GUARDS.variable("already_used"));
    engine.converge(ImmutableList.of(oldAdvertisement, alreadyUsed));
    SymbolicRouteContributionId oldId =
        new SymbolicRouteContributionId(
            oldAdvertisement.getMessageId(),
            oldAdvertisement.getSender(),
            oldAdvertisement.getReceiver());
    SymbolicRouteContributionId missingId =
        new SymbolicRouteContributionId("missing", "origin", "a");

    assertThrows(IllegalArgumentException.class, () -> engine.replace(missingId, alreadyUsed));
    assertThrows(IllegalArgumentException.class, () -> engine.replace(oldId, alreadyUsed));
    assertThat(a.getEntries(), hasSize(2));
  }
}
