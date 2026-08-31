package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Immutable snapshot of guarded SID reachability after underlay convergence. */
public final class GuardedSidDatabase {
  private final ImmutableList<GuardedSidEntry> _entries;

  public static GuardedSidDatabase build(
      Map<String, Configuration> configurations, SymbolicUnderlayReachability underlay) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(underlay, "underlay must be provided");
    List<GuardedSidEntry> entries = new ArrayList<>();
    Set<GuardedSidKey> identities = new HashSet<>();
    for (Map.Entry<String, Configuration> resolver : configurations.entrySet()) {
      for (Configuration owner : configurations.values()) {
        SegmentRoutingConfig sr = owner.getSegmentRoutingConfig();
        if (sr == null) {
          continue;
        }
        sr.getVrfs()
            .forEach(
                (vrf, vrfConfig) -> {
                  if (!resolver.getValue().getVrfs().containsKey(vrf)) {
                    return;
                  }
                  for (SrSidBinding binding : vrfConfig.getSidBindings()) {
                    SrSidBindingKey key = binding.getKey();
                    if (key.getType() == SrSidBindingKey.Type.ADJACENCY) {
                      underlay
                          .adjacencyAvailability(
                              key.getNode(), key.getVrf(), key.getInterfaceName())
                          .filter(value -> value.getGuard().isSatisfiable())
                          .ifPresent(
                              value ->
                                  add(
                                      entries,
                                      identities,
                                      new GuardedSidEntry(
                                          resolver.getKey(),
                                          vrf,
                                          binding,
                                          value.getGuard().simplify(),
                                          value.getFailureKey())));
                      continue;
                    }
                    if ((key.getType() != SrSidBindingKey.Type.PREFIX
                            && key.getType() != SrSidBindingKey.Type.NODE)
                        || key.getPrefix() == null) {
                      continue;
                    }
                    Optional<RouteGuard> guard =
                        underlay.prefixReachability(
                            resolver.getKey(), vrf, key.getPrefix(), key.getAlgorithm());
                    guard
                        .filter(RouteGuard::isSatisfiable)
                        .ifPresent(
                            value -> {
                              GuardedSidEntry entry =
                                  new GuardedSidEntry(
                                      resolver.getKey(), vrf, binding, value.simplify());
                              add(entries, identities, entry);
                            });
                  }
                });
      }
    }
    entries.sort(
        Comparator.comparing(GuardedSidEntry::getResolverNode)
            .thenComparing(GuardedSidEntry::getResolverVrf)
            .thenComparing(entry -> entry.getBinding().getKey().getNode())
            .thenComparing(GuardedSidDatabase::bindingSortKey)
            .thenComparing(entry -> entry.getBinding().getKey().getAlgorithm()));
    return new GuardedSidDatabase(entries);
  }

  private static void add(
      List<GuardedSidEntry> entries, Set<GuardedSidKey> identities, GuardedSidEntry entry) {
    if (!identities.add(entry.getKey())) {
      throw new IllegalArgumentException("duplicate guarded SID identity");
    }
    entries.add(entry);
  }

  private static String bindingSortKey(GuardedSidEntry entry) {
    SrSidBindingKey key = entry.getBinding().getKey();
    return key.getType()
        + ":"
        + (key.getPrefix() == null ? "" : key.getPrefix())
        + ":"
        + (key.getInterfaceName() == null ? "" : key.getInterfaceName());
  }

  private GuardedSidDatabase(List<GuardedSidEntry> entries) {
    _entries = ImmutableList.copyOf(entries);
  }

  public ImmutableList<GuardedSidEntry> getEntries() {
    return _entries;
  }

  public ImmutableList<GuardedSidEntry> getEntries(String node, String vrf) {
    return _entries.stream()
        .filter(entry -> entry.getResolverNode().equals(node) && entry.getResolverVrf().equals(vrf))
        .collect(ImmutableList.toImmutableList());
  }

  ImmutableMap<GuardedSidKey, GuardedSidEntry> asMap() {
    ImmutableMap.Builder<GuardedSidKey, GuardedSidEntry> entries = ImmutableMap.builder();
    _entries.forEach(entry -> entries.put(entry.getKey(), entry));
    return entries.build();
  }
}
