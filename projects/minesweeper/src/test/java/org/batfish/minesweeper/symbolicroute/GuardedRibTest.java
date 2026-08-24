package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.nullValue;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopDiscard;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests of guard algebra and Hoyan-style guarded RIB selection. */
@RunWith(JUnit4.class)
public final class GuardedRibTest {

  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);
  private static final Prefix NETWORK = Prefix.parse("192.0.2.0/24");
  private static final Comparator<StaticRoute> PREFERENCE =
      Comparator.comparingInt(StaticRoute::getAdministrativeCost);

  private static StaticRoute route(int administrativeCost) {
    return StaticRoute.builder()
        .setNetwork(NETWORK)
        .setNextHop(NextHopDiscard.instance())
        .setAdministrativeCost(administrativeCost)
        .build();
  }

  private static SymbolicRoute<StaticRoute> symbolicRoute(
      String source, int administrativeCost, RouteGuard availabilityGuard) {
    return new SymbolicRoute<>(
        new SymbolicRouteKey(
            "r2", RoutingProtocol.STATIC, NETWORK, source, "ad=" + administrativeCost),
        route(administrativeCost),
        availabilityGuard,
        new SymbolicRouteProvenance(
            source, "r2", source, "Ethernet0", ImmutableList.of(source, "r2"), null));
  }

  private static List<GuardedRibUpdateType> updateTypes(GuardedRibDelta<StaticRoute> delta) {
    return delta.getUpdates().stream().map(GuardedRibUpdate::getType).collect(Collectors.toList());
  }

  @Test
  public void testZ3GuardAlgebraAndEquivalence() {
    RouteGuard a = GUARDS.variable("a");
    RouteGuard b = GUARDS.variable("b");

    assertThat(a.and(a.not()).isFalse(), equalTo(true));
    assertThat(a.or(a.not()).isTrue(), equalTo(true));
    assertThat(a.and(b).isEquivalentTo(b.and(a)), equalTo(true));
    assertThat(a.and(b).isSatisfiable(), equalTo(true));
  }

  @Test
  public void testAvailabilityAndSelectionGuardsAreDistinct() {
    RouteGuard lowAvailability = GUARDS.variable("low_available");
    RouteGuard highAvailability = GUARDS.variable("high_available");
    SymbolicRoute<StaticRoute> low = symbolicRoute("low", 20, lowAvailability);
    SymbolicRoute<StaticRoute> high = symbolicRoute("high", 10, highAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    rib.put(low);
    GuardedRibDelta<StaticRoute> lateHighDelta = rib.put(high);

    GuardedRibEntry<StaticRoute> lowEntry = rib.get(low.getKey());
    assertThat(lowEntry == null, equalTo(false));
    assertThat(lowEntry.getAvailabilityGuard().isEquivalentTo(lowAvailability), equalTo(true));
    assertThat(
        lowEntry.getSelectionGuard().isEquivalentTo(lowAvailability.and(highAvailability.not())),
        equalTo(true));
    assertThat(
        rib.get(high.getKey()).getSelectionGuard().isEquivalentTo(highAvailability), equalTo(true));
    assertThat(
        updateTypes(lateHighDelta),
        equalTo(ImmutableList.of(GuardedRibUpdateType.GUARDS_CHANGED, GuardedRibUpdateType.ADDED)));
  }

  @Test
  public void testRemovingHigherRouteRestoresLowerSelectionGuard() {
    RouteGuard lowAvailability = GUARDS.variable("remove_low_available");
    SymbolicRoute<StaticRoute> low = symbolicRoute("remove-low", 20, lowAvailability);
    SymbolicRoute<StaticRoute> high =
        symbolicRoute("remove-high", 10, GUARDS.variable("remove_high_available"));
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    rib.put(low);
    rib.put(high);

    GuardedRibDelta<StaticRoute> delta = rib.remove(high.getKey());

    assertThat(rib.get(high.getKey()), nullValue());
    assertThat(
        rib.get(low.getKey()).getSelectionGuard().isEquivalentTo(lowAvailability), equalTo(true));
    assertThat(
        updateTypes(delta),
        equalTo(
            ImmutableList.of(GuardedRibUpdateType.GUARDS_CHANGED, GuardedRibUpdateType.REMOVED)));
  }

  @Test
  public void testUpdatingHigherAvailabilityRecomputesLowerSelectionGuard() {
    RouteGuard lowAvailability = GUARDS.variable("update_low_available");
    RouteGuard oldHighAvailability = GUARDS.variable("old_high_available");
    RouteGuard newHighAvailability = GUARDS.variable("new_high_available");
    SymbolicRoute<StaticRoute> low = symbolicRoute("update-low", 20, lowAvailability);
    SymbolicRoute<StaticRoute> high = symbolicRoute("update-high", 10, oldHighAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    rib.put(low);
    rib.put(high);

    GuardedRibDelta<StaticRoute> delta = rib.put(high.withAvailabilityGuard(newHighAvailability));

    assertThat(delta.getUpdates(), hasSize(2));
    assertThat(
        rib.get(high.getKey()).getAvailabilityGuard().isEquivalentTo(newHighAvailability),
        equalTo(true));
    assertThat(
        rib.get(low.getKey())
            .getSelectionGuard()
            .isEquivalentTo(lowAvailability.and(newHighAvailability.not())),
        equalTo(true));
  }

  @Test
  public void testEqualPreferenceCandidatesDoNotSuppressEachOther() {
    RouteGuard leftAvailability = GUARDS.variable("left_available");
    RouteGuard rightAvailability = GUARDS.variable("right_available");
    SymbolicRoute<StaticRoute> left = symbolicRoute("left", 10, leftAvailability);
    SymbolicRoute<StaticRoute> right = symbolicRoute("right", 10, rightAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    rib.put(left);
    rib.put(right);

    assertThat(
        rib.get(left.getKey()).getSelectionGuard().isEquivalentTo(leftAvailability), equalTo(true));
    assertThat(
        rib.get(right.getKey()).getSelectionGuard().isEquivalentTo(rightAvailability),
        equalTo(true));
  }

  @Test
  public void testFinalGuardsAreIndependentOfArrivalOrder() {
    SymbolicRoute<StaticRoute> low =
        symbolicRoute("order-low", 20, GUARDS.variable("order_low_available"));
    SymbolicRoute<StaticRoute> high =
        symbolicRoute("order-high", 10, GUARDS.variable("order_high_available"));
    GuardedRib<StaticRoute> lowFirst = new GuardedRib<>(PREFERENCE);
    GuardedRib<StaticRoute> highFirst = new GuardedRib<>(PREFERENCE);

    lowFirst.put(low);
    lowFirst.put(high);
    highFirst.put(high);
    highFirst.put(low);

    assertThat(lowFirst.getEntries(), hasSize(2));
    assertThat(highFirst.getEntries(), hasSize(2));
    assertThat(
        lowFirst
            .get(low.getKey())
            .getSelectionGuard()
            .isEquivalentTo(highFirst.get(low.getKey()).getSelectionGuard()),
        equalTo(true));
    assertThat(
        lowFirst
            .get(high.getKey())
            .getSelectionGuard()
            .isEquivalentTo(highFirst.get(high.getKey()).getSelectionGuard()),
        equalTo(true));
  }

  @Test
  public void testThreePriorityLevelsExcludeEveryStrictlyBetterRoute() {
    RouteGuard highAvailability = GUARDS.variable("three_high_available");
    RouteGuard middleAvailability = GUARDS.variable("three_middle_available");
    RouteGuard lowAvailability = GUARDS.variable("three_low_available");
    SymbolicRoute<StaticRoute> high = symbolicRoute("three-high", 10, highAvailability);
    SymbolicRoute<StaticRoute> middle = symbolicRoute("three-middle", 20, middleAvailability);
    SymbolicRoute<StaticRoute> low = symbolicRoute("three-low", 30, lowAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    rib.put(low);
    rib.put(middle);
    GuardedRibDelta<StaticRoute> lateHighDelta = rib.put(high);

    assertThat(
        rib.get(high.getKey()).getSelectionGuard().isEquivalentTo(highAvailability), equalTo(true));
    assertThat(
        rib.get(middle.getKey())
            .getSelectionGuard()
            .isEquivalentTo(middleAvailability.and(highAvailability.not())),
        equalTo(true));
    assertThat(
        rib.get(low.getKey())
            .getSelectionGuard()
            .isEquivalentTo(
                lowAvailability.and(highAvailability.not()).and(middleAvailability.not())),
        equalTo(true));
    assertThat(lateHighDelta.getUpdates(), hasSize(3));
    assertThat(
        updateTypes(lateHighDelta),
        equalTo(
            ImmutableList.of(
                GuardedRibUpdateType.GUARDS_CHANGED,
                GuardedRibUpdateType.GUARDS_CHANGED,
                GuardedRibUpdateType.ADDED)));
  }

  @Test
  public void testRemovingMiddlePriorityOnlyRestoresLowerRoutes() {
    RouteGuard highAvailability = GUARDS.variable("remove_middle_high_available");
    RouteGuard middleAvailability = GUARDS.variable("remove_middle_available");
    RouteGuard lowAvailability = GUARDS.variable("remove_middle_low_available");
    SymbolicRoute<StaticRoute> high = symbolicRoute("remove-middle-high", 10, highAvailability);
    SymbolicRoute<StaticRoute> middle =
        symbolicRoute("remove-middle-middle", 20, middleAvailability);
    SymbolicRoute<StaticRoute> low = symbolicRoute("remove-middle-low", 30, lowAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    rib.put(high);
    rib.put(middle);
    rib.put(low);

    GuardedRibDelta<StaticRoute> delta = rib.remove(middle.getKey());

    assertThat(delta.getUpdates(), hasSize(2));
    assertThat(
        rib.get(high.getKey()).getSelectionGuard().isEquivalentTo(highAvailability), equalTo(true));
    assertThat(
        rib.get(low.getKey())
            .getSelectionGuard()
            .isEquivalentTo(lowAvailability.and(highAvailability.not())),
        equalTo(true));
    assertThat(
        updateTypes(delta),
        equalTo(
            ImmutableList.of(GuardedRibUpdateType.GUARDS_CHANGED, GuardedRibUpdateType.REMOVED)));
  }

  @Test
  public void testFourPriorityLevelsAccumulateAllHigherAvailabilityGuards() {
    RouteGuard firstAvailability = GUARDS.variable("four_first_available");
    RouteGuard secondAvailability = GUARDS.variable("four_second_available");
    RouteGuard thirdAvailability = GUARDS.variable("four_third_available");
    RouteGuard fourthAvailability = GUARDS.variable("four_fourth_available");
    SymbolicRoute<StaticRoute> first = symbolicRoute("four-first", 10, firstAvailability);
    SymbolicRoute<StaticRoute> second = symbolicRoute("four-second", 20, secondAvailability);
    SymbolicRoute<StaticRoute> third = symbolicRoute("four-third", 30, thirdAvailability);
    SymbolicRoute<StaticRoute> fourth = symbolicRoute("four-fourth", 40, fourthAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    rib.put(fourth);
    rib.put(second);
    rib.put(first);
    rib.put(third);

    assertThat(
        rib.get(fourth.getKey())
            .getSelectionGuard()
            .isEquivalentTo(
                fourthAvailability
                    .and(firstAvailability.not())
                    .and(secondAvailability.not())
                    .and(thirdAvailability.not())),
        equalTo(true));
  }

  @Test
  public void testDuplicateAndEquivalentInsertionsProduceNoUpdates() {
    RouteGuard a = GUARDS.variable("duplicate_a");
    RouteGuard b = GUARDS.variable("duplicate_b");
    SymbolicRoute<StaticRoute> original = symbolicRoute("duplicate", 10, a.and(b));
    SymbolicRoute<StaticRoute> equivalent = original.withAvailabilityGuard(b.and(a));
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    assertThat(rib.put(original).getUpdates(), hasSize(1));
    assertThat(rib.put(original).isEmpty(), equalTo(true));
    assertThat(rib.put(equivalent).isEmpty(), equalTo(true));
    assertThat(rib.getEntries(), hasSize(1));
  }

  @Test
  public void testEqualPriorityGroupIsSuppressedOnlyByStrictlyHigherGroup() {
    RouteGuard highLeftAvailability = GUARDS.variable("group_high_left_available");
    RouteGuard highRightAvailability = GUARDS.variable("group_high_right_available");
    RouteGuard lowLeftAvailability = GUARDS.variable("group_low_left_available");
    RouteGuard lowRightAvailability = GUARDS.variable("group_low_right_available");
    SymbolicRoute<StaticRoute> highLeft =
        symbolicRoute("group-high-left", 10, highLeftAvailability);
    SymbolicRoute<StaticRoute> highRight =
        symbolicRoute("group-high-right", 10, highRightAvailability);
    SymbolicRoute<StaticRoute> lowLeft = symbolicRoute("group-low-left", 20, lowLeftAvailability);
    SymbolicRoute<StaticRoute> lowRight =
        symbolicRoute("group-low-right", 20, lowRightAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    rib.put(lowLeft);
    rib.put(highRight);
    rib.put(lowRight);
    rib.put(highLeft);

    assertThat(
        rib.get(highLeft.getKey()).getSelectionGuard().isEquivalentTo(highLeftAvailability),
        equalTo(true));
    assertThat(
        rib.get(highRight.getKey()).getSelectionGuard().isEquivalentTo(highRightAvailability),
        equalTo(true));
    RouteGuard higherGroupAbsent = highLeftAvailability.not().and(highRightAvailability.not());
    assertThat(
        rib.get(lowLeft.getKey())
            .getSelectionGuard()
            .isEquivalentTo(lowLeftAvailability.and(higherGroupAbsent)),
        equalTo(true));
    assertThat(
        rib.get(lowRight.getKey())
            .getSelectionGuard()
            .isEquivalentTo(lowRightAvailability.and(higherGroupAbsent)),
        equalTo(true));
  }

  @Test
  public void testUnsatisfiableNewCandidateIsNotStored() {
    RouteGuard a = GUARDS.variable("unsat_new");
    SymbolicRoute<StaticRoute> impossible = symbolicRoute("unsat-new", 10, a.and(a.not()));
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);

    assertThat(rib.put(impossible).isEmpty(), equalTo(true));
    assertThat(rib.get(impossible.getKey()), nullValue());
    assertThat(rib.getEntries().isEmpty(), equalTo(true));
  }

  @Test
  public void testUnsatisfiableReplacementRemovesCandidateAndRestoresLowerRoute() {
    RouteGuard highAvailability = GUARDS.variable("unsat_replace_high");
    RouteGuard lowAvailability = GUARDS.variable("unsat_replace_low");
    SymbolicRoute<StaticRoute> high = symbolicRoute("unsat-replace-high", 10, highAvailability);
    SymbolicRoute<StaticRoute> low = symbolicRoute("unsat-replace-low", 20, lowAvailability);
    GuardedRib<StaticRoute> rib = new GuardedRib<>(PREFERENCE);
    rib.put(high);
    rib.put(low);

    GuardedRibDelta<StaticRoute> delta =
        rib.put(high.withAvailabilityGuard(highAvailability.and(highAvailability.not())));

    assertThat(rib.get(high.getKey()), nullValue());
    assertThat(
        rib.get(low.getKey()).getSelectionGuard().isEquivalentTo(lowAvailability), equalTo(true));
    assertThat(
        updateTypes(delta),
        equalTo(
            ImmutableList.of(GuardedRibUpdateType.GUARDS_CHANGED, GuardedRibUpdateType.REMOVED)));
  }
}
