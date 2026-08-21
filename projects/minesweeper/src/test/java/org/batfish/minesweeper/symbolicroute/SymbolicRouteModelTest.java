package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.nullValue;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import java.util.Objects;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of the protocol-neutral symbolic-route data model. */
@RunWith(JUnit4.class)
public final class SymbolicRouteModelTest {

  private static final Prefix NETWORK = Prefix.parse("192.0.2.0/24");

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

  private static final class TestRouteGuard implements RouteGuard {
    private final String _expression;

    private TestRouteGuard(String expression) {
      _expression = expression;
    }

    @Override
    public RouteGuard and(RouteGuard other) {
      return new TestRouteGuard("(" + _expression + " & " + other + ")");
    }

    @Override
    public RouteGuard or(RouteGuard other) {
      return new TestRouteGuard("(" + _expression + " | " + other + ")");
    }

    @Override
    public RouteGuard not() {
      return new TestRouteGuard("!" + _expression);
    }

    @Override
    public RouteGuard simplify() {
      return this;
    }

    @Override
    public boolean isSatisfiable() {
      return !isFalse();
    }

    @Override
    public boolean isEquivalentTo(RouteGuard other) {
      return equals(other);
    }

    @Override
    public boolean isTrue() {
      return _expression.equals("true");
    }

    @Override
    public boolean isFalse() {
      return _expression.equals("false");
    }

    @Override
    public boolean equals(Object o) {
      return this == o
          || o instanceof TestRouteGuard && _expression.equals(((TestRouteGuard) o)._expression);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_expression);
    }

    @Override
    public String toString() {
      return _expression;
    }
  }

  private static StaticRoute staticRoute() {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(1)
        .build();
  }

  private static SymbolicRouteKey key() {
    return new SymbolicRouteKey("r2", RoutingProtocol.STATIC, NETWORK, "r1", "attrs-1");
  }

  private static SymbolicRouteProvenance provenance() {
    return new SymbolicRouteProvenance(
        "r1", "r2", "r1", "Ethernet0", ImmutableList.of("r1", "r2"), "message-0");
  }

  private static SymbolicRoute<StaticRoute> symbolicRoute(RouteGuard guard) {
    return new SymbolicRoute<>(key(), staticRoute(), guard, provenance());
  }

  @Test
  public void testRouteKeyEqualityIncludesEveryIdentityField() {
    SymbolicRouteKey key = key();
    assertThat(
        key, equalTo(new SymbolicRouteKey("r2", RoutingProtocol.STATIC, NETWORK, "r1", "attrs-1")));
    assertThat(
        key,
        not(equalTo(new SymbolicRouteKey("r2", RoutingProtocol.STATIC, NETWORK, "r3", "attrs-1"))));
    assertThat(
        key,
        not(equalTo(new SymbolicRouteKey("r2", RoutingProtocol.STATIC, NETWORK, "r1", "attrs-2"))));
  }

  @Test
  public void testProvenanceDefensivelyCopiesPath() {
    ImmutableList<String> path = ImmutableList.of("r1", "r2", "r3");
    SymbolicRouteProvenance provenance =
        new SymbolicRouteProvenance("r1", "r3", "r2", "Ethernet1", path, "message-1");

    assertThat(provenance.getOriginRouter(), equalTo("r1"));
    assertThat(provenance.getCurrentRouter(), equalTo("r3"));
    assertThat(provenance.getPreviousRouter(), equalTo("r2"));
    assertThat(provenance.getRouterPath(), equalTo(path));
    assertThrows(UnsupportedOperationException.class, () -> provenance.getRouterPath().add("r4"));
  }

  @Test
  public void testProvenanceRejectsInconsistentPath() {
    assertThrows(
        IllegalArgumentException.class,
        () ->
            new SymbolicRouteProvenance(
                "r1", "r3", "r2", null, ImmutableList.of("r2", "r3"), null));
  }

  @Test
  public void testWithPresenceGuardIsImmutable() {
    TestRouteGuard oldGuard = new TestRouteGuard("G1");
    TestRouteGuard newGuard = new TestRouteGuard("G2");
    SymbolicRoute<StaticRoute> original = symbolicRoute(oldGuard);
    SymbolicRoute<StaticRoute> updated = original.withPresenceGuard(newGuard);

    assertThat(original.getPresenceGuard(), equalTo(oldGuard));
    assertThat(updated.getPresenceGuard(), equalTo(newGuard));
    assertThat(updated.getKey(), equalTo(original.getKey()));
    assertThat(updated.getRoute(), equalTo(original.getRoute()));
    assertThat(updated.getProvenance(), equalTo(original.getProvenance()));
  }

  @Test
  public void testMessageDistinguishesPipelineStage() {
    TestRouteGuard guard = new TestRouteGuard("G");
    SymbolicRouteMessage<StaticRoute> message =
        new SymbolicRouteMessage<>(
            "message-1",
            "r1",
            "r2",
            SymbolicRouteMessage.Stage.INGRESS,
            staticRoute(),
            guard,
            provenance());

    assertThat(message.getMessageId(), equalTo("message-1"));
    assertThat(message.getSender(), equalTo("r1"));
    assertThat(message.getReceiver(), equalTo("r2"));
    assertThat(message.getStage(), equalTo(SymbolicRouteMessage.Stage.INGRESS));
    assertThat(message.getGuard(), equalTo(guard));
  }

  @Test
  public void testRibDeltaRepresentsAddChangeAndRemove() {
    SymbolicRoute<StaticRoute> oldRoute = symbolicRoute(new TestRouteGuard("G1"));
    SymbolicRoute<StaticRoute> newRoute = oldRoute.withPresenceGuard(new TestRouteGuard("G2"));
    SymbolicRibUpdate<StaticRoute> added = SymbolicRibUpdate.added(oldRoute);
    SymbolicRibUpdate<StaticRoute> changed =
        SymbolicRibUpdate.presenceGuardChanged(oldRoute, newRoute);
    SymbolicRibUpdate<StaticRoute> removed = SymbolicRibUpdate.removed(newRoute);
    SymbolicRibDelta<StaticRoute> delta =
        new SymbolicRibDelta<>(ImmutableList.of(added, changed, removed));

    assertThat(delta.isEmpty(), equalTo(false));
    assertThat(delta.getUpdates().size(), equalTo(3));
    assertThat(added.getType(), equalTo(SymbolicRibUpdateType.ADDED));
    assertThat(added.getOldRoute(), nullValue());
    assertThat(added.getNewRoute(), equalTo(oldRoute));
    assertThat(changed.getType(), equalTo(SymbolicRibUpdateType.PRESENCE_GUARD_CHANGED));
    assertThat(changed.getOldRoute(), equalTo(oldRoute));
    assertThat(changed.getNewRoute(), equalTo(newRoute));
    assertThat(removed.getType(), equalTo(SymbolicRibUpdateType.REMOVED));
    assertThat(removed.getOldRoute(), equalTo(newRoute));
    assertThat(removed.getNewRoute(), nullValue());
  }

  @Test
  public void testGuardChangeRequiresSameRouteKey() {
    SymbolicRoute<StaticRoute> oldRoute = symbolicRoute(new TestRouteGuard("G1"));
    SymbolicRoute<StaticRoute> differentRoute =
        new SymbolicRoute<>(
            new SymbolicRouteKey(
                "r2", RoutingProtocol.STATIC, NETWORK, "different-source", "attrs-1"),
            staticRoute(),
            new TestRouteGuard("G2"),
            provenance());

    assertThrows(
        IllegalArgumentException.class,
        () -> SymbolicRibUpdate.presenceGuardChanged(oldRoute, differentRoute));
  }
}
