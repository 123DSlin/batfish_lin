package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidResolver;
import org.batfish.datamodel.sr.SrSidValue;

/** Builds an MPLS label plan without collapsing next-hop-dependent SRGB indexes. */
public final class MplsLabelPlanResolver {
  private final ImmutableMap<String, Configuration> _configurations;

  public MplsLabelPlanResolver(Map<String, Configuration> configurations) {
    _configurations = ImmutableMap.copyOf(requireNonNull(configurations));
  }

  public Optional<MplsLabelPlan> resolve(GuardedSegmentList segments) {
    requireNonNull(segments, "guarded segment list must be provided");
    List<MplsLabelInstruction> instructions = new ArrayList<>();
    try {
      for (GuardedSidEntry entry : segments.getSegments()) {
        SrSidBinding binding = entry.getBinding();
        SrSidBindingKey key = binding.getKey();
        SrSidValue sid = binding.getSid();
        if (sid.getType() == SrSidValue.Type.SRV6) {
          return Optional.empty();
        }
        switch (key.getType()) {
          case PREFIX:
          case NODE:
            if (binding.getFlags().contains(SrSidBinding.Flag.LOCAL)) {
              return Optional.empty();
            }
            instructions.add(
                sid.getType() == SrSidValue.Type.MPLS_LABEL
                    ? MplsLabelInstruction.fixed(key, sid)
                    : MplsLabelInstruction.nextHopSrgb(key, sid));
            break;
          case ADJACENCY:
            if (!binding.getFlags().contains(SrSidBinding.Flag.LOCAL)) {
              return Optional.empty();
            }
            Configuration owner = _configurations.get(key.getNode());
            if (owner == null) {
              return Optional.empty();
            }
            SegmentRoutingConfig sr = owner.getSegmentRoutingConfig();
            if (sr == null || !sr.getDataPlanes().contains(SegmentRoutingConfig.DataPlane.MPLS)) {
              return Optional.empty();
            }
            instructions.add(
                MplsLabelInstruction.ownerSrlb(
                    key, sid, key.getNode(), SrSidResolver.resolveLocalMpls(sid, sr.getSrlb())));
            break;
          case BINDING:
          default:
            return Optional.empty();
        }
      }
    } catch (IllegalArgumentException e) {
      return Optional.empty();
    }
    return Optional.of(
        new MplsLabelPlan(
            instructions,
            segments.getAvailabilityGuard(),
            segments.getTerminalNode(),
            segments.getTerminalVrf()));
  }
}
