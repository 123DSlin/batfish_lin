package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/**
 * Protocol-neutral RIB that distinguishes route availability from route selection.
 *
 * <p>The injected comparator must return a negative value when its first route is strictly
 * preferred. Equal routes do not suppress one another, preserving equal-cost alternatives.
 */
public final class GuardedRib<R extends AbstractRouteDecorator> {

  @Nonnull private final Comparator<R> _preferenceComparator;
  @Nonnull private final Map<SymbolicRouteKey, SymbolicRoute<R>> _routes;

  @Nonnull
  private final Map<SymbolicRouteKey, Map<SymbolicRouteContributionId, SymbolicRoute<R>>>
      _contributions;

  public GuardedRib(Comparator<R> preferenceComparator) {
    _preferenceComparator =
        requireNonNull(preferenceComparator, "preferenceComparator must be provided");
    _routes = new LinkedHashMap<>();
    _contributions = new LinkedHashMap<>();
  }

  /** Adds or replaces a candidate and returns every entry affected by the operation. */
  public GuardedRibDelta<R> put(SymbolicRoute<R> route) {
    requireNonNull(route, "route must be provided");
    if (!route.getAvailabilityGuard().isSatisfiable()) {
      return remove(route.getKey());
    }
    Map<SymbolicRouteKey, GuardedRibEntry<R>> before = computeEntries();
    _routes.put(route.getKey(), route);
    return changedEntries(before, computeEntries());
  }

  /** Adds or replaces one advertisement contribution and ORs all contributions to its candidate. */
  public GuardedRibDelta<R> putContribution(
      SymbolicRouteContributionId contributionId, SymbolicRoute<R> route) {
    requireNonNull(contributionId, "contributionId must be provided");
    requireNonNull(route, "route must be provided");
    Map<SymbolicRouteKey, GuardedRibEntry<R>> before = computeEntries();
    Map<SymbolicRouteContributionId, SymbolicRoute<R>> contributions =
        _contributions.computeIfAbsent(route.getKey(), unused -> new LinkedHashMap<>());
    if (route.getAvailabilityGuard().isSatisfiable()) {
      contributions.put(contributionId, route);
    } else {
      contributions.remove(contributionId);
    }
    rebuildCandidate(route.getKey());
    return changedEntries(before, computeEntries());
  }

  /** Withdraws one advertisement contribution without deleting the candidate's other sources. */
  public GuardedRibDelta<R> removeContribution(
      SymbolicRouteKey key, SymbolicRouteContributionId contributionId) {
    requireNonNull(key, "key must be provided");
    requireNonNull(contributionId, "contributionId must be provided");
    Map<SymbolicRouteKey, GuardedRibEntry<R>> before = computeEntries();
    Map<SymbolicRouteContributionId, SymbolicRoute<R>> contributions = _contributions.get(key);
    if (contributions != null) {
      contributions.remove(contributionId);
      rebuildCandidate(key);
    }
    return changedEntries(before, computeEntries());
  }

  /** Removes a candidate and returns every entry affected by the operation. */
  public GuardedRibDelta<R> remove(SymbolicRouteKey key) {
    requireNonNull(key, "key must be provided");
    Map<SymbolicRouteKey, GuardedRibEntry<R>> before = computeEntries();
    _routes.remove(key);
    _contributions.remove(key);
    return changedEntries(before, computeEntries());
  }

  private void rebuildCandidate(SymbolicRouteKey key) {
    Map<SymbolicRouteContributionId, SymbolicRoute<R>> contributions = _contributions.get(key);
    if (contributions == null || contributions.isEmpty()) {
      _contributions.remove(key);
      _routes.remove(key);
      return;
    }
    SymbolicRoute<R> representative = contributions.values().iterator().next();
    RouteGuard availability = representative.getAvailabilityGuard();
    boolean first = true;
    for (SymbolicRoute<R> contribution : contributions.values()) {
      if (!contribution.getRoute().equals(representative.getRoute())) {
        throw new IllegalArgumentException("one candidate cannot contain different route payloads");
      }
      if (first) {
        first = false;
      } else {
        availability = availability.or(contribution.getAvailabilityGuard());
      }
    }
    _routes.put(key, representative.withAvailabilityGuard(availability.simplify()));
  }

  @Nullable
  public GuardedRibEntry<R> get(SymbolicRouteKey key) {
    return computeEntries().get(key);
  }

  public ImmutableList<GuardedRibEntry<R>> getEntries() {
    return ImmutableList.copyOf(computeEntries().values());
  }

  private Map<SymbolicRouteKey, GuardedRibEntry<R>> computeEntries() {
    Map<SymbolicRouteKey, GuardedRibEntry<R>> entries = new LinkedHashMap<>();
    for (SymbolicRoute<R> candidate : _routes.values()) {
      RouteGuard selectionGuard = candidate.getAvailabilityGuard();
      for (SymbolicRoute<R> possibleHigherPriority : _routes.values()) {
        if (sameRibScope(possibleHigherPriority.getKey(), candidate.getKey())
            && _preferenceComparator.compare(
                    possibleHigherPriority.getRoute(), candidate.getRoute())
                < 0) {
          selectionGuard = selectionGuard.and(possibleHigherPriority.getAvailabilityGuard().not());
        }
      }
      entries.put(candidate.getKey(), new GuardedRibEntry<>(candidate, selectionGuard.simplify()));
    }
    return entries;
  }

  private static boolean sameRibScope(SymbolicRouteKey left, SymbolicRouteKey right) {
    return left.getRouter().equals(right.getRouter())
        && left.getVrf().equals(right.getVrf())
        && left.getNetwork().equals(right.getNetwork());
  }

  private static <R extends AbstractRouteDecorator> GuardedRibDelta<R> changedEntries(
      Map<SymbolicRouteKey, GuardedRibEntry<R>> before,
      Map<SymbolicRouteKey, GuardedRibEntry<R>> after) {
    ImmutableList.Builder<GuardedRibUpdate<R>> changed = ImmutableList.builder();
    for (Map.Entry<SymbolicRouteKey, GuardedRibEntry<R>> entry : after.entrySet()) {
      GuardedRibEntry<R> oldEntry = before.get(entry.getKey());
      GuardedRibEntry<R> newEntry = entry.getValue();
      if (oldEntry == null) {
        changed.add(GuardedRibUpdate.added(newEntry));
      } else if (!oldEntry.getAvailabilityGuard().isEquivalentTo(newEntry.getAvailabilityGuard())
          || !oldEntry.getSelectionGuard().isEquivalentTo(newEntry.getSelectionGuard())) {
        changed.add(GuardedRibUpdate.guardsChanged(oldEntry, newEntry));
      }
    }
    for (Map.Entry<SymbolicRouteKey, GuardedRibEntry<R>> entry : before.entrySet()) {
      if (!after.containsKey(entry.getKey())) {
        changed.add(GuardedRibUpdate.removed(entry.getValue()));
      }
    }
    return new GuardedRibDelta<>(changed.build());
  }
}
