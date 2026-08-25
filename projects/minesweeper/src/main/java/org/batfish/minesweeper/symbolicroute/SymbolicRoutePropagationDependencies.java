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

  public SymbolicRoutePropagationDependencies() {
    _children = new LinkedHashMap<>();
  }

  public void addDependency(SymbolicRouteContributionId parent, SymbolicRouteContributionId child) {
    requireNonNull(parent, "parent must be provided");
    requireNonNull(child, "child must be provided");
    _children.computeIfAbsent(parent, unused -> new LinkedHashSet<>()).add(child);
  }

  public ImmutableSet<SymbolicRouteContributionId> getChildren(SymbolicRouteContributionId parent) {
    Set<SymbolicRouteContributionId> children = _children.get(parent);
    return children == null ? ImmutableSet.of() : ImmutableSet.copyOf(children);
  }
}
