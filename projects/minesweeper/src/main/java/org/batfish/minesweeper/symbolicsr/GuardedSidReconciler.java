package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.Map;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;
import org.batfish.minesweeper.symbolicroute.SymbolicRouteNetwork;

/** Keeps the guarded SID snapshot synchronized with stable IS-IS L1/L2 state. */
public final class GuardedSidReconciler {
  private final ImmutableMap<String, Configuration> _configurations;
  private final SymbolicUnderlayReachability _underlay;
  private GuardedSidDatabase _database;
  private GuardedSidDelta _lastDelta;

  public GuardedSidReconciler(
      Map<String, Configuration> configurations,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l1,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> l2) {
    _configurations = ImmutableMap.copyOf(requireNonNull(configurations));
    _underlay = new IsisUnderlayReachability(requireNonNull(l1), requireNonNull(l2));
    _database = GuardedSidDatabase.build(_configurations, _underlay);
    _lastDelta = new GuardedSidDelta(ImmutableList.of());
    l1.getEngine().addStableStateListener(this::reconcile);
    l2.getEngine().addStableStateListener(this::reconcile);
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
    }
    return delta;
  }

  public GuardedSidDatabase getDatabase() {
    return _database;
  }

  public GuardedSidDelta getLastDelta() {
    return _lastDelta;
  }
}
