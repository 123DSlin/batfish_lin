package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One selected guarded forwarding branch emitted by an SR candidate. */
public final class GuardedSrPolicyContribution {
  /** Stable branch identity uses typed forwarding decisions, never route/report text. */
  public static final class Key {
    private final GuardedSrCandidate.Key _candidateKey;
    private final ImmutableList<SymbolicAdjacencyEndpoint> _nextHops;
    private final ImmutableList<LinkFailureKey> _linkDependencies;

    Key(GuardedSrCandidate.Key candidateKey, List<SymbolicNextHopBranch> nextHopDecisions) {
      _candidateKey = requireNonNull(candidateKey);
      _nextHops =
          nextHopDecisions.stream()
              .map(SymbolicNextHopBranch::getNextHop)
              .collect(ImmutableList.toImmutableList());
      _linkDependencies =
          nextHopDecisions.stream()
              .map(SymbolicNextHopBranch::getLinkFailureDependency)
              .collect(ImmutableList.toImmutableList());
    }

    public GuardedSrCandidate.Key getCandidateKey() {
      return _candidateKey;
    }

    public ImmutableList<SymbolicAdjacencyEndpoint> getNextHops() {
      return _nextHops;
    }

    public ImmutableList<LinkFailureKey> getLinkDependencies() {
      return _linkDependencies;
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof Key)) {
        return false;
      }
      Key that = (Key) object;
      return _candidateKey.equals(that._candidateKey)
          && _nextHops.equals(that._nextHops)
          && _linkDependencies.equals(that._linkDependencies);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_candidateKey, _nextHops, _linkDependencies);
    }
  }

  private final Key _key;
  private final GuardedSrCandidate _candidate;
  private final GuardedMplsStackBranch _branch;
  private final RouteGuard _availabilityGuard;
  private final RouteGuard _selectionGuard;
  private final ImmutableSet<GuardedSidKey> _sidDependencies;

  GuardedSrPolicyContribution(
      GuardedSrCandidate candidate,
      GuardedMplsStackBranch branch,
      RouteGuard selectionGuard,
      Set<GuardedSidKey> sidDependencies) {
    _candidate = requireNonNull(candidate);
    _branch = requireNonNull(branch);
    _key = new Key(candidate.getKey(), branch.getNextHopDecisions());
    _availabilityGuard = branch.getGuard();
    _selectionGuard = requireNonNull(selectionGuard);
    _sidDependencies = ImmutableSet.copyOf(requireNonNull(sidDependencies));
  }

  public Key getKey() {
    return _key;
  }

  public GuardedSrCandidate getCandidate() {
    return _candidate;
  }

  public GuardedMplsStackBranch getBranch() {
    return _branch;
  }

  public RouteGuard getAvailabilityGuard() {
    return _availabilityGuard;
  }

  public RouteGuard getSelectionGuard() {
    return _selectionGuard;
  }

  public ImmutableSet<GuardedSidKey> getSidDependencies() {
    return _sidDependencies;
  }

  boolean hasSamePayload(GuardedSrPolicyContribution other) {
    return _branch.getTopFirstLabels().equals(other._branch.getTopFirstLabels())
        && _branch.getTerminalNode().equals(other._branch.getTerminalNode())
        && _branch.getTerminalVrf().equals(other._branch.getTerminalVrf())
        && _sidDependencies.equals(other._sidDependencies);
  }
}
