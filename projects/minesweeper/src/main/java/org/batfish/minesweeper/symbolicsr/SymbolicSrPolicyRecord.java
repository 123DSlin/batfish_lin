package org.batfish.minesweeper.symbolicsr;

import com.google.common.collect.ImmutableList;
import java.util.Comparator;
import java.util.List;
import javax.annotation.Nullable;
import org.batfish.datamodel.sr.SrPolicyEndpoint;
import org.batfish.datamodel.sr.SrPolicyKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Deterministic, serialization-safe view of one guarded SR candidate or forwarding branch. */
public final class SymbolicSrPolicyRecord {
  public enum Kind {
    CANDIDATE,
    FORWARDING_BRANCH
  }

  private final Kind _kind;
  private final String _node;
  private final String _vrf;
  private final long _color;
  private final String _endpoint;
  private final String _policy;
  private final String _candidate;
  private final long _preference;
  private final long _weight;
  private final String _segmentList;
  private final ImmutableList<Long> _labels;
  private final ImmutableList<String> _nextHops;
  private final ImmutableList<String> _linkDependencies;
  @Nullable private final String _terminalNode;
  @Nullable private final String _terminalVrf;
  private final String _availabilityGuard;
  private final String _selectionGuard;

  public static SymbolicSrPolicyRecord fromCandidate(GuardedSrCandidate candidate) {
    return fromCandidate(candidate, true);
  }

  public static SymbolicSrPolicyRecord fromCandidate(
      GuardedSrCandidate candidate, boolean simplifyGuards) {
    SrPolicyKey policyKey = candidate.getKey().getPolicyKey();
    return new SymbolicSrPolicyRecord(
        Kind.CANDIDATE,
        policyKey,
        candidate,
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        null,
        null,
        guardText(candidate.getAvailabilityGuard(), simplifyGuards),
        guardText(candidate.getSelectionGuard(), simplifyGuards));
  }

  public static SymbolicSrPolicyRecord fromContribution(GuardedSrPolicyContribution contribution) {
    return fromContribution(contribution, true);
  }

  public static SymbolicSrPolicyRecord fromContribution(
      GuardedSrPolicyContribution contribution, boolean simplifyGuards) {
    GuardedSrCandidate candidate = contribution.getCandidate();
    SrPolicyKey policyKey = candidate.getKey().getPolicyKey();
    ImmutableList<Long> labels =
        contribution.getBranch().getTopFirstLabels().stream()
            .map(SrSidValue::getMplsLabel)
            .collect(ImmutableList.toImmutableList());
    ImmutableList<String> nextHops =
        contribution.getKey().getNextHops().stream()
            .map(
                nextHop ->
                    nextHop.getNode() + "/" + nextHop.getVrf() + "/" + nextHop.getInterfaceName())
            .collect(ImmutableList.toImmutableList());
    ImmutableList<String> links =
        contribution.getKey().getLinkDependencies().stream()
            .map(link -> link.guardName())
            .collect(ImmutableList.toImmutableList());
    return new SymbolicSrPolicyRecord(
        Kind.FORWARDING_BRANCH,
        policyKey,
        candidate,
        labels,
        nextHops,
        links,
        contribution.getBranch().getTerminalNode(),
        contribution.getBranch().getTerminalVrf(),
        guardText(contribution.getAvailabilityGuard(), simplifyGuards),
        guardText(contribution.getSelectionGuard(), simplifyGuards));
  }

  private static String guardText(RouteGuard guard, boolean simplifyGuards) {
    return (simplifyGuards ? guard.simplifyForDisplay() : guard).toString();
  }

  private SymbolicSrPolicyRecord(
      Kind kind,
      SrPolicyKey policyKey,
      GuardedSrCandidate candidate,
      List<Long> labels,
      List<String> nextHops,
      List<String> linkDependencies,
      @Nullable String terminalNode,
      @Nullable String terminalVrf,
      String availabilityGuard,
      String selectionGuard) {
    _kind = kind;
    _node = policyKey.getNode();
    _vrf = policyKey.getVrf();
    _color = policyKey.getColor();
    _endpoint =
        policyKey.getEndpoint().getFamily() == SrPolicyEndpoint.Family.IPV4
            ? policyKey.getEndpoint().getIpv4().toString()
            : policyKey.getEndpoint().getIpv6().toString();
    _policy = candidate.getPolicyName();
    _candidate = candidate.getCandidate().getName();
    _preference = candidate.getCandidate().getPreference();
    _weight = candidate.getCandidate().getWeight();
    _segmentList = candidate.getCandidate().getSegmentList();
    _labels = ImmutableList.copyOf(labels);
    _nextHops = ImmutableList.copyOf(nextHops);
    _linkDependencies = ImmutableList.copyOf(linkDependencies);
    _terminalNode = terminalNode;
    _terminalVrf = terminalVrf;
    _availabilityGuard = availabilityGuard;
    _selectionGuard = selectionGuard;
  }

  public static Comparator<SymbolicSrPolicyRecord> ordering() {
    return Comparator.comparing(SymbolicSrPolicyRecord::getNode)
        .thenComparing(SymbolicSrPolicyRecord::getVrf)
        .thenComparingLong(SymbolicSrPolicyRecord::getColor)
        .thenComparing(SymbolicSrPolicyRecord::getEndpoint)
        .thenComparing(SymbolicSrPolicyRecord::getCandidate)
        .thenComparing(SymbolicSrPolicyRecord::getKind)
        .thenComparing(record -> record.getLabels().toString())
        .thenComparing(record -> record.getNextHops().toString());
  }

  public Kind getKind() {
    return _kind;
  }

  public String getNode() {
    return _node;
  }

  public String getVrf() {
    return _vrf;
  }

  public long getColor() {
    return _color;
  }

  public String getEndpoint() {
    return _endpoint;
  }

  public String getPolicy() {
    return _policy;
  }

  public String getCandidate() {
    return _candidate;
  }

  public long getPreference() {
    return _preference;
  }

  public long getWeight() {
    return _weight;
  }

  public String getSegmentList() {
    return _segmentList;
  }

  public ImmutableList<Long> getLabels() {
    return _labels;
  }

  public ImmutableList<String> getNextHops() {
    return _nextHops;
  }

  public ImmutableList<String> getLinkDependencies() {
    return _linkDependencies;
  }

  @Nullable
  public String getTerminalNode() {
    return _terminalNode;
  }

  @Nullable
  public String getTerminalVrf() {
    return _terminalVrf;
  }

  public String getAvailabilityGuard() {
    return _availabilityGuard;
  }

  public String getSelectionGuard() {
    return _selectionGuard;
  }
}
