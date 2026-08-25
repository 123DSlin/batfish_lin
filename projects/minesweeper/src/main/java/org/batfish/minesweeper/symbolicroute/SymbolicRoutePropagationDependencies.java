package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

/** Parent-to-child advertisement dependencies used by recursive withdrawal. */
public final class SymbolicRoutePropagationDependencies {

  private final Map<SymbolicRouteContributionId, Set<SymbolicRouteContributionId>> _children;
  private final Map<SymbolicRouteContributionId, Set<SymbolicRouteContributionId>> _parents;

  public SymbolicRoutePropagationDependencies() {
    _children = new LinkedHashMap<>();
    _parents = new LinkedHashMap<>();
  }

  public void addDependency(SymbolicRouteContributionId parent, SymbolicRouteContributionId child) {
    requireNonNull(parent, "parent must be provided");
    requireNonNull(child, "child must be provided");
    _children.computeIfAbsent(parent, unused -> new LinkedHashSet<>()).add(child);
    _parents.computeIfAbsent(child, unused -> new LinkedHashSet<>()).add(parent);
  }

  /** Atomically replaces every parent edge for a child advertisement. */
  public void replaceParents(
      SymbolicRouteContributionId child, Iterable<SymbolicRouteContributionId> parents) {
    requireNonNull(child, "child must be provided");
    requireNonNull(parents, "parents must be provided");
    removeChild(child);
    parents.forEach(parent -> addDependency(parent, child));
  }

  /** Removes a child advertisement and all incoming dependency edges. */
  public void removeChild(SymbolicRouteContributionId child) {
    requireNonNull(child, "child must be provided");
    Set<SymbolicRouteContributionId> parents = _parents.remove(child);
    if (parents == null) {
      return;
    }
    for (SymbolicRouteContributionId parent : parents) {
      Set<SymbolicRouteContributionId> children = _children.get(parent);
      children.remove(child);
      if (children.isEmpty()) {
        _children.remove(parent);
      }
    }
  }

  public ImmutableSet<SymbolicRouteContributionId> getChildren(SymbolicRouteContributionId parent) {
    Set<SymbolicRouteContributionId> children = _children.get(parent);
    return children == null ? ImmutableSet.of() : ImmutableSet.copyOf(children);
  }

  public ImmutableSet<SymbolicRouteContributionId> getParents(SymbolicRouteContributionId child) {
    Set<SymbolicRouteContributionId> parents = _parents.get(child);
    return parents == null ? ImmutableSet.of() : ImmutableSet.copyOf(parents);
  }
}
