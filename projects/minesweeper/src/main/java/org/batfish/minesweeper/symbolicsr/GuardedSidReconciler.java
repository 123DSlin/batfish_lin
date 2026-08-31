package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Consumer;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;
import org.batfish.minesweeper.symbolicroute.BatfishIsisEdge;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteNetwork;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteSession;

/** Keeps the guarded SID snapshot synchronized with stable IS-IS L1/L2 state. */
public final class GuardedSidReconciler {
  private final ImmutableMap<String, Configuration> _configurations;
  private final SymbolicUnderlayReachability _underlay;
  private GuardedSidDatabase _database;
  private GuardedSidDelta _lastDelta;
  private final List<Consumer<GuardedSidDelta>> _deltaListeners;
  private final List<Runnable> _stableStateListeners;

  public GuardedSidReconciler(
      Map<String, Configuration> configurations,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l1,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l2,
      Iterable<BatfishIsisEdge> edges,
      Iterable<SymbolicRouteSession> sessions) {
    this(
        configurations,
        new IsisUnderlayReachability(
            requireNonNull(l1),
            requireNonNull(l2),
            requireNonNull(edges),
            requireNonNull(sessions)));
    l1.getEngine().addStableStateListener(this::reconcile);
    l2.getEngine().addStableStateListener(this::reconcile);
  }

  /** Protocol-neutral stable-underlay wiring, also used by adapter integration tests. */
  public GuardedSidReconciler(
      Map<String, Configuration> configurations, SymbolicUnderlayReachability underlay) {
    _configurations = ImmutableMap.copyOf(requireNonNull(configurations));
    _underlay = requireNonNull(underlay);
    _database = GuardedSidDatabase.build(_configurations, _underlay);
    _lastDelta = new GuardedSidDelta(ImmutableList.of());
    _deltaListeners = new ArrayList<>();
    _stableStateListeners = new ArrayList<>();
  }

  public GuardedSidDelta reconcile() {
    GuardedSidDatabase next = GuardedSidDatabase.build(_configurations, _underlay);
    ImmutableMap<GuardedSidKey, GuardedSidEntry> oldEntries = _database.asMap();
    ImmutableMap<GuardedSidKey, GuardedSidEntry> newEntries = next.asMap();
    ImmutableList.Builder<GuardedSidUpdate> updates = ImmutableList.builder();
    newEntries.forEach(
        (key, entry) -> {
          GuardedSidEntry old = oldEntries.get(key);
          if (old == null) {
            updates.add(GuardedSidUpdate.added(entry));
          } else if (!old.getBinding().equals(entry.getBinding())
              || !Objects.equals(old.getLinkFailureDependency(), entry.getLinkFailureDependency())
              || !Objects.equals(old.getAdjacencyTarget(), entry.getAdjacencyTarget())
              || !old.getAvailabilityGuard().isEquivalentTo(entry.getAvailabilityGuard())) {
            updates.add(GuardedSidUpdate.changed(old, entry));
          }
        });
    oldEntries.forEach(
        (key, entry) -> {
          if (!newEntries.containsKey(key)) {
            updates.add(GuardedSidUpdate.removed(entry));
          }
        });
    _database = next;
    GuardedSidDelta delta = new GuardedSidDelta(updates.build());
    if (!delta.isEmpty()) {
      _lastDelta = delta;
      _deltaListeners.forEach(listener -> listener.accept(delta));
    }
    _stableStateListeners.forEach(Runnable::run);
    return delta;
  }

  public GuardedSidDatabase getDatabase() {
    return _database;
  }

  public GuardedSidDelta getLastDelta() {
    return _lastDelta;
  }

  public SymbolicUnderlayReachability getUnderlay() {
    return _underlay;
  }

  public void addDeltaListener(Consumer<GuardedSidDelta> listener) {
    _deltaListeners.add(requireNonNull(listener));
  }

  /** Runs after every stable underlay reconciliation, including an empty SID delta. */
  public void addStableStateListener(Runnable listener) {
    _stableStateListeners.add(requireNonNull(listener));
  }
}
