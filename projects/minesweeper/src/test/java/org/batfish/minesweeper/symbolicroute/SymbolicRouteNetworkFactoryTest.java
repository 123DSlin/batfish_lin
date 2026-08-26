package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
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

/** Tests of protocol-neutral symbolic route network assembly. */
@RunWith(JUnit4.class)
public final class SymbolicRouteNetworkFactoryTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix NETWORK = Prefix.parse("10.0.0.0/24");

  private static final class TestAdapter implements SymbolicRouteProtocolAdapter<StaticRoute> {

    private final List<String> _importSessionIds = new ArrayList<>();

    @Override
    public Comparator<StaticRoute> preferenceComparator(String receiver) {
      return Comparator.comparingInt(StaticRoute::getAdministrativeCost);
    }

    @Override
    public Optional<StaticRoute> processImport(SymbolicRouteMessage<StaticRoute> message) {
      _importSessionIds.add(message.getSessionId());
      return Optional.of(message.getRoute());
    }

    @Override
    public SymbolicRouteKey createCandidateKey(String receiver, StaticRoute importedRoute) {
      return new SymbolicRouteKey(receiver, "default", importedRoute);
    }

    @Override
    public Optional<StaticRoute> processExport(
        SymbolicRouteSession session, StaticRoute selectedRoute) {
      return Optional.of(selectedRoute);
    }

    @Override
    public String createExportMessageId(
        SymbolicRouteSession session, SymbolicRouteKey candidateKey, StaticRoute exportedRoute) {
      return String.format(
          "%s->%s:%s:%s",
          session.getSender(),
          session.getReceiver(),
          exportedRoute.getNetwork(),
          exportedRoute.getAdministrativeCost());
    }

    List<String> getImportSessionIds() {
      return _importSessionIds;
    }
  }

  private static StaticRoute route(int administrativeCost) {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(administrativeCost)
        .build();
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
  public void testFactoryAssemblesThreeRouterConvergence() {
    StaticRoute route = route(10);
    RouteGuard seedGuard = GUARDS.variable("factory_seed");
    RouteGuard ab = GUARDS.variable("factory_ab");
    RouteGuard bc = GUARDS.variable("factory_bc");
    TestAdapter adapter = new TestAdapter();
    SymbolicRouteNetwork<StaticRoute> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of("a", "b", "c"),
            ImmutableList.of(
                new SymbolicRouteSession("isis:a-b", "a", "b", ab),
                new SymbolicRouteSession("isis:b-c", "b", "c", bc)),
            ImmutableList.of(new SymbolicRouteSeed<>("seed:a", "a", route, seedGuard)),
            adapter);

    SymbolicRouteConvergenceResult result = network.converge();

    assertThat(result.getProcessedMessages(), equalTo(3));
    assertThat(network.getRibs().size(), equalTo(3));
    assertThat(network.getRib("a").getEntries(), hasSize(1));
    assertThat(network.getRib("b").getEntries(), hasSize(1));
    GuardedRibEntry<StaticRoute> atC =
        network.getRib("c").get(new SymbolicRouteKey("c", "default", route));
    assertThat(atC == null, equalTo(false));
    assertThat(atC.getAvailabilityGuard().isEquivalentTo(seedGuard.and(ab).and(bc)), equalTo(true));
    assertThat(adapter.getImportSessionIds(), hasSize(3));
    assertThat(adapter.getImportSessionIds().get(0) == null, equalTo(true));
    assertThat(adapter.getImportSessionIds().get(1), equalTo("isis:a-b"));
    assertThat(adapter.getImportSessionIds().get(2), equalTo("isis:b-c"));
  }

  @Test
  public void testStableAdapterIdentityMakesSeedReplaySemanticNoOp() {
    StaticRoute route = route(10);
    SymbolicRouteNetwork<StaticRoute> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of("a", "b"),
            ImmutableList.of(new SymbolicRouteSession("a", "b", GUARDS.variable("stable_link"))),
            ImmutableList.of(
                new SymbolicRouteSeed<>(
                    "stable_seed", "a", route, GUARDS.variable("stable_seed_guard"))),
            new TestAdapter());
    network.converge();

    SymbolicRouteConvergenceResult replay = network.converge();

    assertThat(replay.getProcessedMessages(), equalTo(1));
    assertThat(replay.getRibUpdates(), equalTo(0));
    assertThat(network.getRib("a").getEntries(), hasSize(1));
    assertThat(network.getRib("b").getEntries(), hasSize(1));
  }

  @Test
  public void testParallelSessionsHaveIndependentContributions() {
    StaticRoute route = route(10);
    RouteGuard seed = GUARDS.variable("parallel_seed");
    RouteGuard firstLink = GUARDS.variable("parallel_first");
    RouteGuard secondLink = GUARDS.variable("parallel_second");
    SymbolicRouteNetwork<StaticRoute> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of("a", "b"),
            ImmutableList.of(
                new SymbolicRouteSession("session-1", "a", "b", firstLink),
                new SymbolicRouteSession("session-2", "a", "b", secondLink)),
            ImmutableList.of(new SymbolicRouteSeed<>("parallel", "a", route, seed)),
            new TestAdapter());

    network.converge();

    SymbolicRouteKey key = new SymbolicRouteKey("b", "default", route);
    GuardedRibEntry<StaticRoute> atB = network.getRib("b").get(key);
    assertThat(atB == null, equalTo(false));
    assertThat(
        atB.getAvailabilityGuard().isEquivalentTo(seed.and(firstLink.or(secondLink))),
        equalTo(true));
    assertThat(network.getRib("b").getContributionIds(key), hasSize(2));
  }

  @Test
  public void testFactoryRejectsInvalidTopologyReferences() {
    TestAdapter adapter = new TestAdapter();
    StaticRoute route = route(10);
    RouteGuard guard = GUARDS.variable("invalid_topology");

    assertThrows(
        IllegalArgumentException.class,
        () ->
            SymbolicRouteNetworkFactory.create(
                ImmutableList.of("a", "a"), ImmutableList.of(), ImmutableList.of(), adapter));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            SymbolicRouteNetworkFactory.create(
                ImmutableList.of("a"),
                ImmutableList.of(new SymbolicRouteSession("a", "b", guard)),
                ImmutableList.of(),
                adapter));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            SymbolicRouteNetworkFactory.create(
                ImmutableList.of("a"),
                ImmutableList.of(),
                ImmutableList.of(new SymbolicRouteSeed<>("unknown", "b", route, guard)),
                adapter));
    assertThrows(IllegalArgumentException.class, () -> new SymbolicRouteSession("a", "a", guard));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            SymbolicRouteNetworkFactory.create(
                ImmutableList.of("a", "b"),
                ImmutableList.of(
                    new SymbolicRouteSession("same", "a", "b", guard),
                    new SymbolicRouteSession("same", "b", "a", guard)),
                ImmutableList.of(),
                adapter));
    assertThrows(
        IllegalArgumentException.class,
        () ->
            SymbolicRouteNetworkFactory.create(
                ImmutableList.of("a"),
                ImmutableList.of(),
                ImmutableList.of(
                    new SymbolicRouteSeed<>("same", "a", route, guard),
                    new SymbolicRouteSeed<>("same", "a", route, guard)),
                adapter));
  }

  @Test
  public void testNetworkReturnsImmutableRibRegistryAndRejectsUnknownRouter() {
    SymbolicRouteNetwork<StaticRoute> network =
        SymbolicRouteNetworkFactory.create(
            ImmutableList.of("a"), ImmutableList.of(), ImmutableList.of(), new TestAdapter());

    assertThrows(
        UnsupportedOperationException.class,
        () -> network.getRibs().put("b", new GuardedRib<>(Comparator.comparingInt(r -> 0))));
    assertThrows(IllegalArgumentException.class, () -> network.getRib("missing"));
  }
}
