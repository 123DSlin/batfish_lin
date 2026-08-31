package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SegmentRoutingVrfConfig;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrPolicy;
import org.batfish.datamodel.sr.SrSegmentList;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Immutable selected SR-policy state derived from one stable underlay/SID snapshot. */
public final class GuardedSrPolicyDatabase {
  private static final class ResolvedCandidate {
    private final SrCandidatePath _candidate;
    private final GuardedSegmentList _segments;
    private final ImmutableList<GuardedMplsStackBranch> _branches;
    private final RouteGuard _availabilityGuard;

    private ResolvedCandidate(
        SrCandidatePath candidate,
        GuardedSegmentList segments,
        ImmutableList<GuardedMplsStackBranch> branches,
        RouteGuard availabilityGuard) {
      _candidate = candidate;
      _segments = segments;
      _branches = branches;
      _availabilityGuard = availabilityGuard;
    }
  }

  private final ImmutableList<GuardedSrCandidate> _candidates;
  private final ImmutableList<GuardedSrPolicyContribution> _contributions;

  public static GuardedSrPolicyDatabase build(
      Map<String, Configuration> configurations,
      GuardedSidDatabase sidDatabase,
      SymbolicUnderlayReachability underlay) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(sidDatabase, "SID database must be provided");
    requireNonNull(underlay, "underlay must be provided");
    GuardedSegmentListResolver segmentResolver = new GuardedSegmentListResolver(sidDatabase);
    MplsLabelPlanResolver planResolver = new MplsLabelPlanResolver(configurations);
    MplsNumericStackResolver stackResolver = new MplsNumericStackResolver(configurations, underlay);
    List<GuardedSrCandidate> candidates = new ArrayList<>();
    Map<GuardedSrPolicyContribution.Key, GuardedSrPolicyContribution> contributions =
        new LinkedHashMap<>();
    for (Configuration configuration : configurations.values()) {
      SegmentRoutingConfig sr = configuration.getSegmentRoutingConfig();
      if (sr == null) {
        continue;
      }
      for (SegmentRoutingVrfConfig vrf : sr.getVrfs().values()) {
        Map<String, SrSegmentList> segmentLists = new HashMap<>();
        vrf.getSegmentLists()
            .forEach(segmentList -> segmentLists.put(segmentList.getKey().getName(), segmentList));
        for (SrPolicy policy : vrf.getPolicies()) {
          List<ResolvedCandidate> resolved =
              resolveCandidates(policy, segmentLists, segmentResolver, planResolver, stackResolver);
          for (ResolvedCandidate current : resolved) {
            RouteGuard blocker = null;
            for (ResolvedCandidate possibleHigher : resolved) {
              if (possibleHigher._candidate.getPreference() > current._candidate.getPreference()) {
                blocker =
                    blocker == null
                        ? possibleHigher._availabilityGuard
                        : blocker.or(possibleHigher._availabilityGuard);
              }
            }
            RouteGuard selectionGuard =
                blocker == null
                    ? current._availabilityGuard
                    : current._availabilityGuard.and(blocker.not()).simplify();
            GuardedSrCandidate guardedCandidate =
                new GuardedSrCandidate(
                    policy.getKey(),
                    policy.getName(),
                    current._candidate,
                    current._availabilityGuard,
                    selectionGuard);
            candidates.add(guardedCandidate);
            Set<GuardedSidKey> sidDependencies =
                current._segments.getSegments().stream()
                    .map(GuardedSidEntry::getKey)
                    .collect(ImmutableSet.toImmutableSet());
            for (GuardedMplsStackBranch branch : current._branches) {
              RouteGuard branchSelection =
                  blocker == null
                      ? branch.getGuard()
                      : branch.getGuard().and(blocker.not()).simplify();
              if (!branchSelection.isSatisfiable()) {
                continue;
              }
              GuardedSrPolicyContribution contribution =
                  new GuardedSrPolicyContribution(
                      guardedCandidate, branch, branchSelection, sidDependencies);
              merge(contributions, contribution);
            }
          }
        }
      }
    }
    candidates.sort(Comparator.comparing(GuardedSrPolicyDatabase::candidateSortKey));
    List<GuardedSrPolicyContribution> orderedContributions =
        new ArrayList<>(contributions.values());
    orderedContributions.sort(Comparator.comparing(GuardedSrPolicyDatabase::contributionSortKey));
    return new GuardedSrPolicyDatabase(candidates, orderedContributions);
  }

  private static List<ResolvedCandidate> resolveCandidates(
      SrPolicy policy,
      Map<String, SrSegmentList> segmentLists,
      GuardedSegmentListResolver segmentResolver,
      MplsLabelPlanResolver planResolver,
      MplsNumericStackResolver stackResolver) {
    List<ResolvedCandidate> resolved = new ArrayList<>();
    for (SrCandidatePath candidate : policy.getCandidates()) {
      SrSegmentList segmentList = segmentLists.get(candidate.getSegmentList());
      if (segmentList == null) {
        continue;
      }
      Optional<GuardedSegmentList> guardedSegments =
          segmentResolver.resolve(policy.getKey().getNode(), policy.getKey().getVrf(), segmentList);
      if (!guardedSegments.isPresent()) {
        continue;
      }
      Optional<MplsLabelPlan> plan = planResolver.resolve(guardedSegments.get());
      if (!plan.isPresent()) {
        continue;
      }
      ImmutableList<GuardedMplsStackBranch> branches = stackResolver.resolve(plan.get());
      RouteGuard availability = union(branches);
      if (availability == null || !availability.isSatisfiable()) {
        continue;
      }
      resolved.add(
          new ResolvedCandidate(
              candidate, guardedSegments.get(), branches, availability.simplify()));
    }
    return resolved;
  }

  private static RouteGuard union(List<GuardedMplsStackBranch> branches) {
    RouteGuard guard = null;
    for (GuardedMplsStackBranch branch : branches) {
      guard = guard == null ? branch.getGuard() : guard.or(branch.getGuard());
    }
    return guard;
  }

  private static void merge(
      Map<GuardedSrPolicyContribution.Key, GuardedSrPolicyContribution> contributions,
      GuardedSrPolicyContribution contribution) {
    GuardedSrPolicyContribution old = contributions.get(contribution.getKey());
    if (old == null) {
      contributions.put(contribution.getKey(), contribution);
      return;
    }
    if (!old.hasSamePayload(contribution)) {
      throw new IllegalArgumentException("conflicting SR forwarding branch identity");
    }
    RouteGuard availability =
        old.getAvailabilityGuard().or(contribution.getAvailabilityGuard()).simplify();
    RouteGuard selection = old.getSelectionGuard().or(contribution.getSelectionGuard()).simplify();
    GuardedMplsStackBranch branch =
        new GuardedMplsStackBranch(
            old.getBranch().getTopFirstLabels(),
            old.getBranch().getNextHopDecisions(),
            availability,
            old.getBranch().getTerminalNode(),
            old.getBranch().getTerminalVrf());
    contributions.put(
        old.getKey(),
        new GuardedSrPolicyContribution(
            old.getCandidate(), branch, selection, old.getSidDependencies()));
  }

  private static String candidateSortKey(GuardedSrCandidate candidate) {
    return candidate.getKey().getPolicyKey().getNode()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getVrf()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getColor()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getEndpoint().getFamily()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getEndpoint().getIpv4()
        + "\u0000"
        + candidate.getKey().getPolicyKey().getEndpoint().getIpv6()
        + "\u0000"
        + candidate.getKey().getCandidateName();
  }

  private static String contributionSortKey(GuardedSrPolicyContribution contribution) {
    StringBuilder key = new StringBuilder(candidateSortKey(contribution.getCandidate()));
    contribution
        .getKey()
        .getNextHops()
        .forEach(
            nextHop ->
                key.append('\u0000')
                    .append(nextHop.getNode())
                    .append('\u0000')
                    .append(nextHop.getVrf())
                    .append('\u0000')
                    .append(nextHop.getInterfaceName()));
    contribution
        .getKey()
        .getLinkDependencies()
        .forEach(
            dependency ->
                key.append('\u0000')
                    .append(dependency.getFirstRouter())
                    .append('\u0000')
                    .append(dependency.getSecondRouter()));
    return key.toString();
  }

  private GuardedSrPolicyDatabase(
      Iterable<GuardedSrCandidate> candidates,
      Iterable<GuardedSrPolicyContribution> contributions) {
    _candidates = ImmutableList.copyOf(candidates);
    _contributions = ImmutableList.copyOf(contributions);
  }

  public ImmutableList<GuardedSrCandidate> getCandidates() {
    return _candidates;
  }

  public ImmutableList<GuardedSrPolicyContribution> getContributions() {
    return _contributions;
  }

  ImmutableMap<GuardedSrCandidate.Key, GuardedSrCandidate> candidatesByKey() {
    return _candidates.stream()
        .collect(ImmutableMap.toImmutableMap(GuardedSrCandidate::getKey, candidate -> candidate));
  }

  ImmutableMap<GuardedSrPolicyContribution.Key, GuardedSrPolicyContribution> contributionsByKey() {
    return _contributions.stream()
        .collect(
            ImmutableMap.toImmutableMap(
                GuardedSrPolicyContribution::getKey, contribution -> contribution));
  }
}
