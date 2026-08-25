package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.util.Optional;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of Hoyan-style egress, link guards, advertisement, and propagation dependencies. */
@RunWith(JUnit4.class)
public final class SymbolicRouteExporterTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix NETWORK = Prefix.parse("203.0.113.0/24");

  private static StaticRoute route(int administrativeCost) {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(administrativeCost)
        .build();
  }

  private static GuardedRibEntry<StaticRoute> entry(
      RouteGuard availabilityGuard, RouteGuard selectionGuard) {
    StaticRoute route = route(10);
    return new GuardedRibEntry<>(
        new SymbolicRoute<>(
            new SymbolicRouteKey("sender", "default", route),
            route,
            availabilityGuard,
            new SymbolicRouteProvenance(
                "origin",
                "sender",
                "origin",
                "Ethernet0",
                ImmutableList.of("origin", "sender"),
                "root")),
        selectionGuard);
  }

  private static SymbolicRouteExporter<StaticRoute> exporter(
      RouteGuard linkGuard,
      SymbolicRouteEgressPolicy<StaticRoute> policy,
      SymbolicRoutePropagationDependencies dependencies) {
    return new SymbolicRouteExporter<>(
        "sender",
        "receiver",
        linkGuard,
        policy,
        (sender, receiver, route) -> sender + "->" + receiver + ":route",
        dependencies);
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
  public void testExportUsesSelectionGuardAndLinkGuard() {
    RouteGuard availability = GUARDS.variable("export_availability");
    RouteGuard selection = GUARDS.variable("export_selection");
    RouteGuard link = GUARDS.variable("export_link");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    SymbolicRouteMessage<StaticRoute> message =
        exporter(link, (sender, receiver, route) -> Optional.of(route), dependencies)
            .export(entry(availability, selection), ImmutableList.of())
            .get();

    assertThat(message.getGuard().isEquivalentTo(selection.and(link)), equalTo(true));
    assertThat(message.getGuard().isEquivalentTo(availability.and(link)), equalTo(false));
    assertThat(message.getStage(), equalTo(SymbolicRouteMessage.Stage.INGRESS));
    assertThat(message.getSender(), equalTo("sender"));
    assertThat(message.getReceiver(), equalTo("receiver"));
  }

  @Test
  public void testEgressDenyProducesNoAdvertisementOrDependency() {
    SymbolicRouteContributionId parent =
        new SymbolicRouteContributionId("parent", "origin", "sender");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    Optional<SymbolicRouteMessage<StaticRoute>> result =
        exporter(
                GUARDS.variable("deny_link"),
                (sender, receiver, route) -> Optional.empty(),
                dependencies)
            .export(
                entry(GUARDS.variable("deny_availability"), GUARDS.variable("deny_selection")),
                ImmutableList.of(parent));

    assertThat(result.isPresent(), equalTo(false));
    assertThat(dependencies.getChildren(parent).isEmpty(), equalTo(true));
  }

  @Test
  public void testUnsatisfiableSelectionAndLinkProducesNoAdvertisement() {
    RouteGuard link = GUARDS.variable("unsat_link");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    Optional<SymbolicRouteMessage<StaticRoute>> result =
        exporter(link, (sender, receiver, route) -> Optional.of(route), dependencies)
            .export(entry(GUARDS.variable("unsat_availability"), link.not()), ImmutableList.of());

    assertThat(result.isPresent(), equalTo(false));
  }

  @Test
  public void testEgressTransformationIsCarriedByAdvertisement() {
    StaticRoute transformed = route(20);
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    SymbolicRouteMessage<StaticRoute> message =
        exporter(
                GUARDS.variable("transform_link"),
                (sender, receiver, route) -> Optional.of(transformed),
                dependencies)
            .export(
                entry(
                    GUARDS.variable("transform_availability"),
                    GUARDS.variable("transform_selection")),
                ImmutableList.of())
            .get();

    assertThat(message.getRoute(), equalTo(transformed));
  }

  @Test
  public void testEveryParentRecordsSameChildDependency() {
    SymbolicRouteContributionId left =
        new SymbolicRouteContributionId("left", "left-router", "sender");
    SymbolicRouteContributionId right =
        new SymbolicRouteContributionId("right", "right-router", "sender");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    SymbolicRouteMessage<StaticRoute> message =
        exporter(
                GUARDS.variable("dependency_link"),
                (sender, receiver, route) -> Optional.of(route),
                dependencies)
            .export(
                entry(
                    GUARDS.variable("dependency_availability"),
                    GUARDS.variable("dependency_selection")),
                ImmutableList.of(left, right))
            .get();
    SymbolicRouteContributionId child =
        new SymbolicRouteContributionId(
            message.getMessageId(), message.getSender(), message.getReceiver());

    assertThat(dependencies.getChildren(left), hasSize(1));
    assertThat(dependencies.getChildren(left).contains(child), equalTo(true));
    assertThat(dependencies.getChildren(right).contains(child), equalTo(true));
  }

  @Test
  public void testExportExtendsProvenancePath() {
    SymbolicRouteContributionId parent =
        new SymbolicRouteContributionId("parent", "origin", "sender");
    SymbolicRouteMessage<StaticRoute> message =
        exporter(
                GUARDS.variable("path_link"),
                (sender, receiver, route) -> Optional.of(route),
                new SymbolicRoutePropagationDependencies())
            .export(
                entry(GUARDS.variable("path_availability"), GUARDS.variable("path_selection")),
                ImmutableList.of(parent))
            .get();

    assertThat(
        message.getProvenance().getRouterPath(),
        equalTo(ImmutableList.of("origin", "sender", "receiver")));
    assertThat(message.getProvenance().getParentMessageId(), equalTo("parent"));
  }

  @Test
  public void testRejectsEntryFromDifferentSender() {
    GuardedRibEntry<StaticRoute> entry =
        entry(GUARDS.variable("owner_availability"), GUARDS.variable("owner_selection"));
    SymbolicRouteExporter<StaticRoute> wrongExporter =
        new SymbolicRouteExporter<>(
            "other",
            "receiver",
            GUARDS.variable("owner_link"),
            (sender, receiver, route) -> Optional.of(route),
            (sender, receiver, route) -> "message",
            new SymbolicRoutePropagationDependencies());

    assertThrows(
        IllegalArgumentException.class, () -> wrongExporter.export(entry, ImmutableList.of()));
  }
}
