package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;
import static org.junit.Assert.fail;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
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
        (sender, receiver, key, route) -> sender + "->" + receiver + ":route",
        dependencies);
  }

  private static SymbolicRouteContributionId parent(String messageId) {
    return new SymbolicRouteContributionId(messageId, "origin", "sender");
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
            .export(entry(availability, selection), parent("export-parent"))
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
                parent);

    assertThat(result.isPresent(), equalTo(false));
    assertThat(dependencies.getChildren(parent).isEmpty(), equalTo(true));
  }

  @Test
  public void testUnsatisfiableSelectionAndLinkProducesNoAdvertisement() {
    RouteGuard link = GUARDS.variable("unsat_link");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    Optional<SymbolicRouteMessage<StaticRoute>> result =
        exporter(link, (sender, receiver, route) -> Optional.of(route), dependencies)
            .export(entry(GUARDS.variable("unsat_availability"), link.not()), parent("unsat"));

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
                parent("transform"))
            .get();

    assertThat(message.getRoute(), equalTo(transformed));
  }

  @Test
  public void testEachParentProducesIndependentChildDependency() {
    SymbolicRouteContributionId left =
        new SymbolicRouteContributionId("left", "left-router", "sender");
    SymbolicRouteContributionId right =
        new SymbolicRouteContributionId("right", "right-router", "sender");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();

    SymbolicRouteExporter<StaticRoute> exporter =
        exporter(
            GUARDS.variable("dependency_link"),
            (sender, receiver, route) -> Optional.of(route),
            dependencies);
    GuardedRibEntry<StaticRoute> entry =
        entry(GUARDS.variable("dependency_availability"), GUARDS.variable("dependency_selection"));
    SymbolicRouteMessage<StaticRoute> leftMessage = exporter.export(entry, left).get();
    SymbolicRouteMessage<StaticRoute> rightMessage = exporter.export(entry, right).get();
    SymbolicRouteContributionId leftChild =
        new SymbolicRouteContributionId(
            leftMessage.getMessageId(), leftMessage.getSender(), leftMessage.getReceiver());
    SymbolicRouteContributionId rightChild =
        new SymbolicRouteContributionId(
            rightMessage.getMessageId(), rightMessage.getSender(), rightMessage.getReceiver());

    assertThat(dependencies.getChildren(left), hasSize(1));
    assertThat(dependencies.getChildren(left), equalTo(ImmutableSet.of(leftChild)));
    assertThat(dependencies.getChildren(right), equalTo(ImmutableSet.of(rightChild)));
    assertThat(leftChild.equals(rightChild), equalTo(false));
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
                parent)
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
            (sender, receiver, key, route) -> "message",
            new SymbolicRoutePropagationDependencies());

    assertThrows(
        IllegalArgumentException.class, () -> wrongExporter.export(entry, parent("wrong-owner")));
  }

  @Test
  public void testReexportReplacesParentDependencies() {
    SymbolicRouteContributionId stableParent =
        new SymbolicRouteContributionId("stable-parent", "old", "sender");
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();
    SymbolicRouteExporter<StaticRoute> exporter =
        exporter(
            GUARDS.variable("replace_link"),
            (sender, receiver, route) -> Optional.of(route),
            dependencies);
    GuardedRibEntry<StaticRoute> entry =
        entry(GUARDS.variable("replace_availability"), GUARDS.variable("replace_selection"));

    SymbolicRouteMessage<StaticRoute> first = exporter.export(entry, stableParent).get();
    SymbolicRouteMessage<StaticRoute> second = exporter.export(entry, stableParent).get();
    SymbolicRouteContributionId child =
        new SymbolicRouteContributionId(
            second.getMessageId(), second.getSender(), second.getReceiver());

    assertThat(first.getMessageId(), equalTo(second.getMessageId()));
    assertThat(dependencies.getChildren(stableParent), equalTo(ImmutableSet.of(child)));
    assertThat(dependencies.getParents(child), equalTo(ImmutableSet.of(stableParent)));
  }
}
