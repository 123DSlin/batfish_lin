package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Resolves an ordered typed SID sequence over one stable guarded SID snapshot. */
public final class GuardedSegmentListResolver {
  private final GuardedSidDatabase _database;

  public GuardedSegmentListResolver(GuardedSidDatabase database) {
    _database = requireNonNull(database, "SID database must be provided");
  }

  public Optional<GuardedSegmentList> resolve(
      String ingressNode, String ingressVrf, List<SrSidBindingKey> segments) {
    requireNonNull(ingressNode, "ingress node must be provided");
    requireNonNull(ingressVrf, "ingress VRF must be provided");
    requireNonNull(segments, "segments must be provided");
    if (segments.isEmpty()) {
      throw new IllegalArgumentException("segment list must not be empty");
    }
    String currentNode = ingressNode;
    String currentVrf = ingressVrf;
    RouteGuard guard = null;
    List<GuardedSidEntry> resolved = new ArrayList<>();
    for (SrSidBindingKey key : segments) {
      if (key.getType() == SrSidBindingKey.Type.BINDING) {
        return Optional.empty();
      }
      Optional<GuardedSidEntry> candidate = _database.getEntry(currentNode, currentVrf, key);
      if (!candidate.isPresent()) {
        return Optional.empty();
      }
      GuardedSidEntry entry = candidate.get();
      RouteGuard nextGuard = entry.getAvailabilityGuard();
      guard = guard == null ? nextGuard : guard.and(nextGuard);
      if (!guard.isSatisfiable()) {
        return Optional.empty();
      }
      resolved.add(entry);
      if (key.getType() == SrSidBindingKey.Type.ADJACENCY) {
        if (!entry.getBinding().getFlags().contains(SrSidBinding.Flag.LOCAL)
            || !currentNode.equals(key.getNode())
            || !currentVrf.equals(key.getVrf())) {
          return Optional.empty();
        }
        SymbolicAdjacencyEndpoint target = entry.getAdjacencyTarget();
        if (target == null) {
          return Optional.empty();
        }
        currentNode = target.getNode();
        currentVrf = target.getVrf();
      } else {
        currentNode = key.getNode();
        currentVrf = key.getVrf();
      }
    }
    assert guard != null;
    return Optional.of(new GuardedSegmentList(resolved, guard.simplify(), currentNode, currentVrf));
  }
}
