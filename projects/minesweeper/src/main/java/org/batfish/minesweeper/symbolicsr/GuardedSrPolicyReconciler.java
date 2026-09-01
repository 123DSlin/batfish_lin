package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.Map;
import org.batfish.datamodel.Configuration;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/**
 * Reconciles selected SR forwarding outputs across stable underlay boundaries for fixed SR
 * configuration and emits atomic semantic lifecycle deltas.
 */
public final class GuardedSrPolicyReconciler {
  private final ImmutableMap<String, Configuration> _configurations;
  private final SymbolicUnderlayReachability _underlay;
  private GuardedSidDatabase _sidDatabase;
  private GuardedSrPolicyDatabase _database;
  private GuardedSrPolicyDelta _lastDelta;

  /** Production wiring: every stable underlay boundary reconciles dependent policy output. */
  public GuardedSrPolicyReconciler(
      Map<String, Configuration> configurations, GuardedSidReconciler sidReconciler) {
    this(configurations, sidReconciler.getUnderlay(), sidReconciler.getDatabase());
    sidReconciler.addStableStateListener(
        () -> {
          _sidDatabase = sidReconciler.getDatabase();
          reconcile();
        });
  }

  /** Explicit snapshot wiring for tests and callers that own the stable-state boundary. */
  public GuardedSrPolicyReconciler(
      Map<String, Configuration> configurations,
      SymbolicUnderlayReachability underlay,
      GuardedSidDatabase sidDatabase) {
    _configurations = ImmutableMap.copyOf(requireNonNull(configurations));
    _underlay = requireNonNull(underlay);
    _sidDatabase = requireNonNull(sidDatabase);
    _database = GuardedSrPolicyDatabase.build(_configurations, _sidDatabase, _underlay);
    _lastDelta = new GuardedSrPolicyDelta(ImmutableList.of(), ImmutableList.of());
  }

  public GuardedSrPolicyDelta reconcile() {
    GuardedSrPolicyDatabase next =
        GuardedSrPolicyDatabase.build(_configurations, _sidDatabase, _underlay);
    GuardedSrPolicyDelta delta = difference(_database, next);
    _database = next;
    if (!delta.isEmpty()) {
      _lastDelta = delta;
    }
    return delta;
  }

  /** Reconciles an explicitly supplied stable SID snapshot. */
  public GuardedSrPolicyDelta reconcile(GuardedSidDatabase sidDatabase) {
    _sidDatabase = requireNonNull(sidDatabase);
    return reconcile();
  }

  public GuardedSrPolicyDatabase getDatabase() {
    return _database;
  }

  public GuardedSrPolicyDelta getLastDelta() {
    return _lastDelta;
  }

  private static GuardedSrPolicyDelta difference(
      GuardedSrPolicyDatabase oldDatabase, GuardedSrPolicyDatabase newDatabase) {
    ImmutableList.Builder<GuardedSrPolicyDelta.Update<GuardedSrCandidate>> candidateUpdates =
        ImmutableList.builder();
    ImmutableMap<GuardedSrCandidate.Key, GuardedSrCandidate> oldCandidates =
        oldDatabase.candidatesByKey();
    ImmutableMap<GuardedSrCandidate.Key, GuardedSrCandidate> newCandidates =
        newDatabase.candidatesByKey();
    newCandidates.forEach(
        (key, candidate) -> {
          GuardedSrCandidate old = oldCandidates.get(key);
          if (old == null) {
            candidateUpdates.add(GuardedSrPolicyDelta.Update.added(candidate));
          } else if (!old.getCandidate().equals(candidate.getCandidate())) {
            candidateUpdates.add(
                GuardedSrPolicyDelta.Update.changed(
                    GuardedSrPolicyDelta.Type.REPLACED, old, candidate));
          } else if (guardsChanged(
              old.getAvailabilityGuard(),
              candidate.getAvailabilityGuard(),
              old.getSelectionGuard(),
              candidate.getSelectionGuard())) {
            candidateUpdates.add(
                GuardedSrPolicyDelta.Update.changed(
                    GuardedSrPolicyDelta.Type.GUARD_CHANGED, old, candidate));
          }
        });
    oldCandidates.forEach(
        (key, candidate) -> {
          if (!newCandidates.containsKey(key)) {
            candidateUpdates.add(GuardedSrPolicyDelta.Update.removed(candidate));
          }
        });

    ImmutableList.Builder<GuardedSrPolicyDelta.Update<GuardedSrPolicyContribution>>
        contributionUpdates = ImmutableList.builder();
    ImmutableMap<GuardedSrPolicyContribution.Key, GuardedSrPolicyContribution> oldContributions =
        oldDatabase.contributionsByKey();
    ImmutableMap<GuardedSrPolicyContribution.Key, GuardedSrPolicyContribution> newContributions =
        newDatabase.contributionsByKey();
    newContributions.forEach(
        (key, contribution) -> {
          GuardedSrPolicyContribution old = oldContributions.get(key);
          if (old == null) {
            contributionUpdates.add(GuardedSrPolicyDelta.Update.added(contribution));
          } else if (!old.hasSamePayload(contribution)
              || !old.getCandidate()
                  .getCandidate()
                  .equals(contribution.getCandidate().getCandidate())) {
            contributionUpdates.add(
                GuardedSrPolicyDelta.Update.changed(
                    GuardedSrPolicyDelta.Type.REPLACED, old, contribution));
          } else if (guardsChanged(
              old.getAvailabilityGuard(),
              contribution.getAvailabilityGuard(),
              old.getSelectionGuard(),
              contribution.getSelectionGuard())) {
            contributionUpdates.add(
                GuardedSrPolicyDelta.Update.changed(
                    GuardedSrPolicyDelta.Type.GUARD_CHANGED, old, contribution));
          }
        });
    oldContributions.forEach(
        (key, contribution) -> {
          if (!newContributions.containsKey(key)) {
            contributionUpdates.add(GuardedSrPolicyDelta.Update.removed(contribution));
          }
        });
    return new GuardedSrPolicyDelta(candidateUpdates.build(), contributionUpdates.build());
  }

  private static boolean guardsChanged(
      RouteGuard oldAvailability,
      RouteGuard newAvailability,
      RouteGuard oldSelection,
      RouteGuard newSelection) {
    return !oldAvailability.isEquivalentTo(newAvailability)
        || !oldSelection.isEquivalentTo(newSelection);
  }
}
