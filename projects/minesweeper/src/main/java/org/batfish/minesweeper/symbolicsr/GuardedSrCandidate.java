package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import org.batfish.datamodel.sr.SrCandidatePath;
import org.batfish.datamodel.sr.SrPolicyKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One configured SR candidate with distinct availability and preference-selection guards. */
public final class GuardedSrCandidate {
  /** Stable identity excludes preference, weight, guards, and resolved forwarding payload. */
  public static final class Key {
    private final SrPolicyKey _policyKey;
    private final String _candidateName;

    public Key(SrPolicyKey policyKey, String candidateName) {
      _policyKey = requireNonNull(policyKey);
      _candidateName = requireNonNull(candidateName);
    }

    public SrPolicyKey getPolicyKey() {
      return _policyKey;
    }

    public String getCandidateName() {
      return _candidateName;
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
      return _policyKey.equals(that._policyKey) && _candidateName.equals(that._candidateName);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_policyKey, _candidateName);
    }
  }

  private final Key _key;
  private final String _policyName;
  private final SrCandidatePath _candidate;
  private final RouteGuard _availabilityGuard;
  private final RouteGuard _selectionGuard;

  GuardedSrCandidate(
      SrPolicyKey policyKey,
      String policyName,
      SrCandidatePath candidate,
      RouteGuard availabilityGuard,
      RouteGuard selectionGuard) {
    _key = new Key(policyKey, candidate.getName());
    _policyName = requireNonNull(policyName);
    _candidate = requireNonNull(candidate);
    _availabilityGuard = requireNonNull(availabilityGuard);
    _selectionGuard = requireNonNull(selectionGuard);
  }

  public Key getKey() {
    return _key;
  }

  public String getPolicyName() {
    return _policyName;
  }

  public SrCandidatePath getCandidate() {
    return _candidate;
  }

  public RouteGuard getAvailabilityGuard() {
    return _availabilityGuard;
  }

  public RouteGuard getSelectionGuard() {
    return _selectionGuard;
  }
}
