package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.nullValue;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of Hoyan Algorithm 1 initialization, queue, ingress-policy, and RIB-update steps. */
@RunWith(JUnit4.class)
public final class SymbolicRouteIngressProcessorTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix NETWORK = Prefix.parse("198.51.100.0/24");
  private static final Comparator<StaticRoute> PREFERENCE =
      Comparator.comparingInt(StaticRoute::getAdministrativeCost);

  private static StaticRoute route(int administrativeCost) {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(administrativeCost)
        .build();
  }

  private static SymbolicRouteMessage<StaticRoute> message(
      String messageId, String sender, StaticRoute route, RouteGuard guard) {
    return new SymbolicRouteMessage<>(
        messageId,
        sender,
        "receiver",
        SymbolicRouteMessage.Stage.INGRESS,
        route,
        guard,
        new SymbolicRouteProvenance(
            sender, "receiver", sender, "Ethernet0", ImmutableList.of(sender, "receiver"), null));
  }

  private static SymbolicRouteIngressProcessor<StaticRoute> processor(
      GuardedRib<StaticRoute> rib, SymbolicRouteIngressPolicy<StaticRoute> policy) {
    return new SymbolicRouteIngressProcessor<>(
        "receiver",
        rib,
        policy,
        (receiver, route) -> new SymbolicRouteKey(receiver, "default", route));
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
  public void testInitialAdvertisementsAreProcessedInFifoOrder() {
    List<String> processed = new ArrayList<>();
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(
            rib,
            message -> {
              processed.add(message.getMessageId());
              return Optional.of(message.getRoute());
            });

    processor.process(
        ImmutableList.of(
            message("m1", "r1", route(10), GUARDS.variable("fifo_1")),
            message("m2", "r2", route(20), GUARDS.variable("fifo_2")),
            message("m3", "r3", route(30), GUARDS.variable("fifo_3"))));

    assertThat(processed, equalTo(ImmutableList.of("m1", "m2", "m3")));
    assertThat(processor.isQueueEmpty(), equalTo(true));
    assertThat(rib.getEntries(), hasSize(3));
  }

  @Test
  public void testDeniedAdvertisementDoesNotReachRib() {
    StaticRoute denied = route(10);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(rib, message -> Optional.empty());

    assertThat(
        processor.process(
            ImmutableList.of(message("denied", "r1", denied, GUARDS.variable("deny_guard")))),
        hasSize(0));
    assertThat(rib.get(new SymbolicRouteKey("receiver", "default", denied)), nullValue());
  }

  @Test
  public void testIngressTransformationDeterminesCandidateKeyAndPayload() {
    StaticRoute input = route(20);
    StaticRoute transformed = route(10);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(rib, message -> Optional.of(transformed));

    processor.process(
        ImmutableList.of(message("transformed", "r1", input, GUARDS.variable("transform_guard"))));

    assertThat(rib.get(new SymbolicRouteKey("receiver", "default", input)), nullValue());
    assertThat(
        rib.get(new SymbolicRouteKey("receiver", "default", transformed)) == null, equalTo(false));
  }

  @Test
  public void testEquivalentReplayProducesNoDelta() {
    RouteGuard a = GUARDS.variable("ingress_replay_a");
    RouteGuard b = GUARDS.variable("ingress_replay_b");
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(rib, message -> Optional.of(message.getRoute()));

    assertThat(
        processor.process(ImmutableList.of(message("replay", "r1", route, a.and(b)))), hasSize(1));
    assertThat(
        processor.process(ImmutableList.of(message("replay", "r1", route, b.and(a)))), hasSize(0));
    assertThat(rib.getEntries(), hasSize(1));
  }

  @Test
  public void testEqualCandidateAdvertisementsMergeAvailability() {
    RouteGuard left = GUARDS.variable("ingress_left");
    RouteGuard right = GUARDS.variable("ingress_right");
    StaticRoute route = route(10);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(rib, message -> Optional.of(message.getRoute()));

    processor.process(
        ImmutableList.of(message("left", "r1", route, left), message("right", "r2", route, right)));

    assertThat(rib.getEntries(), hasSize(1));
    assertThat(
        rib.get(new SymbolicRouteKey("receiver", "default", route))
            .getAvailabilityGuard()
            .isEquivalentTo(left.or(right)),
        equalTo(true));
  }

  @Test
  public void testRejectsEgressMessageAtIngressBoundary() {
    StaticRoute route = route(10);
    SymbolicRouteMessage<StaticRoute> ingress =
        message("wrong-stage", "r1", route, GUARDS.variable("wrong_stage"));
    SymbolicRouteMessage<StaticRoute> egress =
        new SymbolicRouteMessage<>(
            ingress.getMessageId(),
            ingress.getSender(),
            ingress.getReceiver(),
            SymbolicRouteMessage.Stage.EGRESS,
            ingress.getRoute(),
            ingress.getGuard(),
            ingress.getProvenance());
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(new GuardedRib<>(PREFERENCE), message -> Optional.of(message.getRoute()));

    assertThrows(IllegalArgumentException.class, () -> processor.process(ImmutableList.of(egress)));
    assertThat(processor.isQueueEmpty(), equalTo(true));
  }

  @Test
  public void testRejectsMessageForDifferentReceiver() {
    StaticRoute route = route(10);
    SymbolicRouteMessage<StaticRoute> original =
        message("wrong-receiver", "r1", route, GUARDS.variable("wrong_receiver"));
    SymbolicRouteMessage<StaticRoute> wrongReceiver =
        new SymbolicRouteMessage<>(
            original.getMessageId(),
            original.getSender(),
            "other-router",
            original.getStage(),
            original.getRoute(),
            original.getGuard(),
            original.getProvenance());
    SymbolicRouteIngressProcessor<StaticRoute> processor =
        processor(new GuardedRib<>(PREFERENCE), message -> Optional.of(message.getRoute()));

    assertThrows(
        IllegalArgumentException.class, () -> processor.process(ImmutableList.of(wrongReceiver)));
  }
}
