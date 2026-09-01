package org.batfish.minesweeper.symbolicsr;

import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import com.microsoft.z3.Context;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrGlobalBlock;
import org.batfish.datamodel.sr.SrLabelRange;
import org.batfish.datamodel.sr.SrPolicy;
import org.batfish.datamodel.sr.SrPolicyEndpoint;
import org.batfish.datamodel.sr.SrPolicyKey;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.datamodel.sr.SrSegment;
import org.batfish.datamodel.sr.SrSegmentList;
import org.batfish.datamodel.sr.SrSegmentListKey;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests SR candidate selection and dependent forwarding-output lifecycle. */
@RunWith(JUnit4.class)
public final class GuardedSrPolicyReconcilerTest {
  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  private static final class PrefixState {
    private final String _owner;
    private RouteGuard _guard;

    private PrefixState(String owner, RouteGuard guard) {
      _owner = owner;
      _guard = guard;
    }
  }

  private static final class MutableUnderlay implements SymbolicUnderlayReachability {
    private final Map<SrPrefix, PrefixState> _prefixes = new HashMap<>();

    void put(SrPrefix prefix, String owner, RouteGuard guard) {
      _prefixes.put(prefix, new PrefixState(owner, guard));
    }

    void setGuard(SrPrefix prefix, RouteGuard guard) {
      _prefixes.get(prefix)._guard = guard;
    }

    void setOwner(SrPrefix prefix, String owner) {
      PrefixState old = _prefixes.get(prefix);
      _prefixes.put(prefix, new PrefixState(owner, old._guard));
    }

    @Override
    public Optional<RouteGuard> prefixReachability(
        String node, String vrf, SrPrefix prefix, int algorithm) {
      PrefixState state = _prefixes.get(prefix);
      return state == null ? Optional.empty() : Optional.of(state._guard);
    }

    @Override
    public ImmutableList<SymbolicNextHopBranch> prefixNextHops(
        String node, String vrf, SrPrefix prefix, int algorithm) {
      PrefixState state = _prefixes.get(prefix);
      if (state == null || node.equals(state._owner)) {
        return ImmutableList.of();
      }
      return ImmutableList.of(
          new SymbolicNextHopBranch(
              new SymbolicAdjacencyEndpoint(state._owner, vrf, "to-" + state._owner),
              LinkFailureKey.of(node, state._owner),
              state._guard));
    }
  }

  private static final class Fixture {
    private final ImmutableMap<String, Configuration> _configurations;
    private final MutableUnderlay _underlay;
    private final ImmutableMap<String, SrPrefix> _prefixes;

    private Fixture(
        ImmutableMap<String, Configuration> configurations,
        MutableUnderlay underlay,
        ImmutableMap<String, SrPrefix> prefixes) {
      _configurations = configurations;
      _underlay = underlay;
      _prefixes = prefixes;
    }
  }

  @Test
  public void testThreePriorityGroupsAndEqualPreferenceDoNotSuppressEachOther() {
    RouteGuard high = GUARDS.variable("high");
    RouteGuard middleLeft = GUARDS.variable("middleLeft");
    RouteGuard middleRight = GUARDS.variable("middleRight");
    RouteGuard low = GUARDS.variable("low");
    Fixture fixture = fixture(high, middleLeft, middleRight, low);
    GuardedSrPolicyDatabase database =
        GuardedSrPolicyDatabase.build(
            fixture._configurations,
            GuardedSidDatabase.build(fixture._configurations, fixture._underlay),
            fixture._underlay);

    assertThat(database.getCandidates(), hasSize(4));
    assertEquivalent(candidate(database, "high").getSelectionGuard(), high);
    assertEquivalent(
        candidate(database, "middle-left").getSelectionGuard(), middleLeft.and(high.not()));
    assertEquivalent(
        candidate(database, "middle-right").getSelectionGuard(), middleRight.and(high.not()));
    assertEquivalent(
        candidate(database, "low").getSelectionGuard(),
        low.and(high.not()).and(middleLeft.not()).and(middleRight.not()));
    assertThat(database.getContributions(), hasSize(4));
    GuardedSrPolicyContribution highOutput = contribution(database, "high");
    assertThat(highOutput.getSidDependencies(), hasSize(1));
    assertThat(highOutput.getKey().getLinkDependencies(), hasSize(1));
  }

  @Test
  public void testGuardChangeAndRecursiveDependencyWithdrawal() {
    RouteGuard high = GUARDS.variable("highLifecycle");
    RouteGuard middleLeft = GUARDS.variable("middleLeftLifecycle");
    RouteGuard middleRight = GUARDS.variable("middleRightLifecycle");
    RouteGuard low = GUARDS.variable("lowLifecycle");
    Fixture fixture = fixture(high, middleLeft, middleRight, low);
    GuardedSidReconciler sidReconciler =
        new GuardedSidReconciler(fixture._configurations, fixture._underlay);
    GuardedSrPolicyReconciler reconciler =
        new GuardedSrPolicyReconciler(fixture._configurations, sidReconciler);

    fixture._underlay.setGuard(fixture._prefixes.get("high"), high.or(GUARDS.variable("extra")));
    sidReconciler.reconcile();
    GuardedSrPolicyDelta guardDelta = reconciler.getLastDelta();
    assertThat(
        updateType(guardDelta, "high", true), equalTo(GuardedSrPolicyDelta.Type.GUARD_CHANGED));
    assertThat(
        updateType(guardDelta, "high", false), equalTo(GuardedSrPolicyDelta.Type.GUARD_CHANGED));

    fixture._underlay.setGuard(fixture._prefixes.get("high"), GUARDS.falseGuard());
    sidReconciler.reconcile();
    GuardedSrPolicyDelta withdrawalDelta = reconciler.getLastDelta();
    assertThat(
        updateType(withdrawalDelta, "high", true), equalTo(GuardedSrPolicyDelta.Type.REMOVED));
    assertThat(
        updateType(withdrawalDelta, "high", false), equalTo(GuardedSrPolicyDelta.Type.REMOVED));
    assertEquivalent(
        candidate(reconciler.getDatabase(), "middle-left").getSelectionGuard(), middleLeft);
  }

  @Test
  public void testBindingPayloadChangeReplacesForwardingOutput() {
    SrSidBindingKey bindingKey = bindingKey("r1", 11);
    SrPrefix prefix = bindingKey.getPrefix();
    MutableUnderlay underlay = new MutableUnderlay();
    underlay.put(prefix, "r1", GUARDS.trueGuard());
    SrSegmentList segmentList =
        new SrSegmentList(
            new SrSegmentListKey("r0", DEFAULT_VRF_NAME, "path"),
            ImmutableList.of(new SrSegment(10L, bindingKey, null)));
    SrPolicy policy = policy(candidate("stable", 100, "path"));
    ImmutableMap<String, Configuration> configurations =
        ImmutableMap.of(
            "r0", policyConfiguration("r0", ImmutableList.of(segmentList), policy),
            "r1", plainConfiguration("r1"));
    GuardedSidEntry oldEntry =
        new GuardedSidEntry(
            "r0",
            DEFAULT_VRF_NAME,
            new SrSidBinding(bindingKey, SrSidValue.mplsLabel(16001L), ImmutableSet.of()),
            GUARDS.trueGuard());
    GuardedSrPolicyReconciler reconciler =
        new GuardedSrPolicyReconciler(
            configurations, underlay, new GuardedSidDatabase(ImmutableList.of(oldEntry)));
    GuardedSidEntry replacement =
        new GuardedSidEntry(
            "r0",
            DEFAULT_VRF_NAME,
            new SrSidBinding(bindingKey, SrSidValue.mplsLabel(16002L), ImmutableSet.of()),
            GUARDS.trueGuard());

    GuardedSrPolicyDelta delta =
        reconciler.reconcile(new GuardedSidDatabase(ImmutableList.of(replacement)));
    assertThat(delta.getCandidateUpdates(), hasSize(0));
    assertThat(delta.getContributionUpdates(), hasSize(1));
    assertThat(
        delta.getContributionUpdates().get(0).getType(),
        equalTo(GuardedSrPolicyDelta.Type.REPLACED));
    assertThat(
        delta.getContributionUpdates().get(0).getOldValue().getKey(),
        equalTo(delta.getContributionUpdates().get(0).getNewValue().getKey()));
    assertThat(
        reconciler.getDatabase().getContributions().get(0).getBranch().getTopFirstLabels().get(0),
        equalTo(SrSidValue.mplsLabel(16002L)));
  }

  @Test
  public void testNextHopChangeWithEquivalentSidGuardStillReconciles() {
    Fixture fixture =
        fixture(
            GUARDS.variable("stableHigh"),
            GUARDS.variable("stableMiddleLeft"),
            GUARDS.variable("stableMiddleRight"),
            GUARDS.variable("stableLow"));
    GuardedSidReconciler sidReconciler =
        new GuardedSidReconciler(fixture._configurations, fixture._underlay);
    GuardedSrPolicyReconciler reconciler =
        new GuardedSrPolicyReconciler(fixture._configurations, sidReconciler);

    fixture._underlay.setOwner(fixture._prefixes.get("high"), "r5");
    GuardedSidDelta sidDelta = sidReconciler.reconcile();

    assertThat(sidDelta.isEmpty(), equalTo(true));
    assertThat(reconciler.getLastDelta().getCandidateUpdates(), hasSize(0));
    assertThat(reconciler.getLastDelta().getContributionUpdates(), hasSize(2));
    assertThat(
        reconciler.getLastDelta().getContributionUpdates().stream()
            .anyMatch(update -> update.getType() == GuardedSrPolicyDelta.Type.REMOVED),
        equalTo(true));
    assertThat(
        reconciler.getLastDelta().getContributionUpdates().stream()
            .anyMatch(update -> update.getType() == GuardedSrPolicyDelta.Type.ADDED),
        equalTo(true));
    GuardedSrPolicyDelta.Update<GuardedSrPolicyContribution> removed =
        reconciler.getLastDelta().getContributionUpdates().stream()
            .filter(update -> update.getType() == GuardedSrPolicyDelta.Type.REMOVED)
            .findFirst()
            .get();
    GuardedSrPolicyDelta.Update<GuardedSrPolicyContribution> added =
        reconciler.getLastDelta().getContributionUpdates().stream()
            .filter(update -> update.getType() == GuardedSrPolicyDelta.Type.ADDED)
            .findFirst()
            .get();
    assertThat(removed.getOldValue().getKey().equals(added.getNewValue().getKey()), equalTo(false));
    assertThat(
        reconciler.getDatabase().getContributions().contains(added.getNewValue()), equalTo(true));
    assertThat(
        reconciler.getDatabase().getContributions().contains(removed.getOldValue()),
        equalTo(false));
  }

  @Test
  public void testExplicitSidAmbiguityFailsClosed() {
    SrSidValue sid = SrSidValue.mplsLabel(16001L);
    GuardedSidDatabase database =
        new GuardedSidDatabase(
            ImmutableList.of(
                entry("r1", 1, sid, GUARDS.trueGuard()), entry("r2", 2, sid, GUARDS.trueGuard())));
    SrSegmentList segmentList =
        new SrSegmentList(
            new SrSegmentListKey("r0", DEFAULT_VRF_NAME, "ambiguous"),
            ImmutableList.of(new SrSegment(10L, null, sid)));

    assertThat(
        new GuardedSegmentListResolver(database)
            .resolve("r0", DEFAULT_VRF_NAME, segmentList)
            .isPresent(),
        equalTo(false));
  }

  private static Fixture fixture(
      RouteGuard high, RouteGuard middleLeft, RouteGuard middleRight, RouteGuard low) {
    ImmutableMap<String, SrPrefix> prefixes =
        ImmutableMap.of(
            "high", prefix(1),
            "middle-left", prefix(2),
            "middle-right", prefix(3),
            "low", prefix(4));
    MutableUnderlay underlay = new MutableUnderlay();
    underlay.put(prefixes.get("high"), "r1", high);
    underlay.put(prefixes.get("middle-left"), "r2", middleLeft);
    underlay.put(prefixes.get("middle-right"), "r3", middleRight);
    underlay.put(prefixes.get("low"), "r4", low);
    ImmutableList<SrSegmentList> lists =
        ImmutableList.of(
            explicitList("high", 16001L),
            explicitList("middle-left", 16002L),
            explicitList("middle-right", 16003L),
            explicitList("low", 16004L));
    SrPolicy policy =
        policy(
            candidate("high", 300, "high"),
            candidate("middle-left", 200, "middle-left"),
            candidate("middle-right", 200, "middle-right"),
            candidate("low", 100, "low"));
    ImmutableMap.Builder<String, Configuration> configurations = ImmutableMap.builder();
    configurations.put("r0", policyConfiguration("r0", lists, policy));
    for (int i = 1; i <= 4; i++) {
      configurations.put("r" + i, bindingConfiguration("r" + i, i, 16000L + i));
    }
    configurations.put("r5", plainConfiguration("r5"));
    return new Fixture(configurations.build(), underlay, prefixes);
  }

  private static Configuration bindingConfiguration(String node, int id, long label) {
    Configuration configuration = plainConfiguration(node);
    SrSidBinding binding =
        new SrSidBinding(bindingKey(node, id), SrSidValue.mplsLabel(label), ImmutableSet.of());
    configuration.setSegmentRoutingConfig(
        srConfig(
            ImmutableMap.of(
                DEFAULT_VRF_NAME,
                new SegmentRoutingVrfConfig(
                    DEFAULT_VRF_NAME, ImmutableList.of(binding), null, null))));
    return configuration;
  }

  private static Configuration policyConfiguration(
      String node, ImmutableList<SrSegmentList> lists, SrPolicy policy) {
    Configuration configuration = plainConfiguration(node);
    configuration.setSegmentRoutingConfig(
        srConfig(
            ImmutableMap.of(
                DEFAULT_VRF_NAME,
                new SegmentRoutingVrfConfig(
                    DEFAULT_VRF_NAME, ImmutableList.of(), lists, ImmutableList.of(policy)))));
    return configuration;
  }

  private static Configuration plainConfiguration(String node) {
    NetworkFactory nf = new NetworkFactory();
    Configuration configuration =
        nf.configurationBuilder()
            .setHostname(node)
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    nf.vrfBuilder().setOwner(configuration).setName(DEFAULT_VRF_NAME).build();
    return configuration;
  }

  private static SegmentRoutingConfig srConfig(Map<String, SegmentRoutingVrfConfig> vrfs) {
    return new SegmentRoutingConfig(
        ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
        SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 23999L))),
        null,
        vrfs);
  }

  private static SrPolicy policy(SrCandidatePath... candidates) {
    return new SrPolicy(
        new SrPolicyKey("r0", DEFAULT_VRF_NAME, 50L, SrPolicyEndpoint.ipv4(Ip.parse("10.0.0.9"))),
        "policy",
        ImmutableList.copyOf(candidates));
  }

  private static SrCandidatePath candidate(String name, long preference, String list) {
    return new SrCandidatePath(name, preference, 1L, list);
  }

  private static SrSegmentList explicitList(String name, long label) {
    return new SrSegmentList(
        new SrSegmentListKey("r0", DEFAULT_VRF_NAME, name),
        ImmutableList.of(new SrSegment(10L, null, SrSidValue.mplsLabel(label))));
  }

  private static SrSidBindingKey bindingKey(String owner, int id) {
    return new SrSidBindingKey(
        owner, DEFAULT_VRF_NAME, SrSidBindingKey.Type.PREFIX, 0, prefix(id), null, null);
  }

  private static SrPrefix prefix(int id) {
    return SrPrefix.ipv4(Prefix.parse("10.0.0." + id + "/32"));
  }

  private static GuardedSidEntry entry(String owner, int id, SrSidValue sid, RouteGuard guard) {
    return new GuardedSidEntry(
        "r0",
        DEFAULT_VRF_NAME,
        new SrSidBinding(bindingKey(owner, id), sid, ImmutableSet.of()),
        guard);
  }

  private static GuardedSrCandidate candidate(GuardedSrPolicyDatabase database, String name) {
    return database.getCandidates().stream()
        .filter(candidate -> candidate.getCandidate().getName().equals(name))
        .findFirst()
        .get();
  }

  private static GuardedSrPolicyContribution contribution(
      GuardedSrPolicyDatabase database, String candidateName) {
    return database.getContributions().stream()
        .filter(
            contribution ->
                contribution.getCandidate().getCandidate().getName().equals(candidateName))
        .findFirst()
        .get();
  }

  private static GuardedSrPolicyDelta.Type updateType(
      GuardedSrPolicyDelta delta, String candidateName, boolean candidateUpdate) {
    if (candidateUpdate) {
      return delta.getCandidateUpdates().stream()
          .filter(
              update ->
                  (update.getNewValue() != null ? update.getNewValue() : update.getOldValue())
                      .getCandidate()
                      .getName()
                      .equals(candidateName))
          .findFirst()
          .get()
          .getType();
    }
    return delta.getContributionUpdates().stream()
        .filter(
            update ->
                (update.getNewValue() != null ? update.getNewValue() : update.getOldValue())
                    .getCandidate()
                    .getCandidate()
                    .getName()
                    .equals(candidateName))
        .findFirst()
        .get()
        .getType();
  }

  private static void assertEquivalent(RouteGuard actual, RouteGuard expected) {
    assertThat(actual.isEquivalentTo(expected), equalTo(true));
  }
}
