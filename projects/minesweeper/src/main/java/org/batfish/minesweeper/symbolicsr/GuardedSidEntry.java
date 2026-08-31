package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** One SID binding reachable from a particular node/VRF under a symbolic guard. */
public final class GuardedSidEntry {
  private final GuardedSidKey _key;
  private final SrSidBinding _binding;
  private final RouteGuard _availabilityGuard;

  GuardedSidEntry(
      String resolverNode, String resolverVrf, SrSidBinding binding, RouteGuard availabilityGuard) {
    _binding = requireNonNull(binding, "binding must be provided");
    _key = new GuardedSidKey(resolverNode, resolverVrf, binding.getKey());
    _availabilityGuard = requireNonNull(availabilityGuard, "guard must be provided");
  }

  public String getResolverNode() {
    return _key.getResolverNode();
  }

  public String getResolverVrf() {
    return _key.getResolverVrf();
  }

  public GuardedSidKey getKey() {
    return _key;
  }

  public SrSidBinding getBinding() {
    return _binding;
  }

  public RouteGuard getAvailabilityGuard() {
    return _availabilityGuard;
  }
}
