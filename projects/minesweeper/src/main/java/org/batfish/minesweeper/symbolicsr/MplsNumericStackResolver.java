package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/** Materializes one numeric MPLS stack per satisfiable guarded next-hop combination. */
public final class MplsNumericStackResolver {
  private final ImmutableMap<String, Configuration> _configurations;
  private final SymbolicUnderlayReachability _underlay;

  public MplsNumericStackResolver(
      Map<String, Configuration> configurations, SymbolicUnderlayReachability underlay) {
    _configurations = ImmutableMap.copyOf(requireNonNull(configurations));
    _underlay = requireNonNull(underlay);
  }

  public ImmutableList<GuardedMplsStackBranch> resolve(MplsLabelPlan plan) {
    requireNonNull(plan, "MPLS label plan must be provided");
    List<State> states = new ArrayList<>();
    states.add(new State(ImmutableList.of(), ImmutableList.of(), plan.getAvailabilityGuard()));
    for (MplsLabelInstruction instruction : plan.getTopFirstInstructions()) {
      SrSidBindingKey key = instruction.getBindingKey();
      boolean prefixOrNode =
          key.getType() == SrSidBindingKey.Type.PREFIX
              || key.getType() == SrSidBindingKey.Type.NODE;
      if (!prefixOrNode) {
        SrSidValue label = instruction.getResolvedLabel();
        if (label == null) {
          return ImmutableList.of();
        }
        states.forEach(state -> state._labels.add(label));
        continue;
      }
      String forwardingNode = instruction.getForwardingNode();
      String forwardingVrf = instruction.getForwardingVrf();
      SrPrefix prefix = key.getPrefix();
      if (forwardingNode == null || forwardingVrf == null || prefix == null) {
        return ImmutableList.of();
      }
      ImmutableList<SymbolicNextHopBranch> nextHops =
          _underlay.prefixNextHops(forwardingNode, forwardingVrf, prefix, key.getAlgorithm());
      List<State> expanded = new ArrayList<>();
      for (State state : states) {
        for (SymbolicNextHopBranch nextHop : nextHops) {
          RouteGuard guard = state._guard.and(nextHop.getGuard()).simplify();
          if (!guard.isSatisfiable()) {
            continue;
          }
          Configuration nextHopConfiguration = _configurations.get(nextHop.getNextHop().getNode());
          if (nextHopConfiguration == null) {
            continue;
          }
          Optional<SrSidValue> resolved = resolveLabel(instruction, nextHopConfiguration);
          if (!resolved.isPresent()) {
            continue;
          }
          List<SrSidValue> labels = new ArrayList<>(state._labels);
          labels.add(resolved.get());
          List<SymbolicNextHopBranch> decisions = new ArrayList<>(state._nextHopDecisions);
          decisions.add(nextHop);
          expanded.add(new State(labels, decisions, guard));
        }
      }
      states = expanded;
      if (states.isEmpty()) {
        return ImmutableList.of();
      }
    }
    return states.stream()
        .map(
            state ->
                new GuardedMplsStackBranch(
                    state._labels,
                    state._nextHopDecisions,
                    state._guard,
                    plan.getTerminalNode(),
                    plan.getTerminalVrf()))
        .collect(ImmutableList.toImmutableList());
  }

  private static Optional<SrSidValue> resolveLabel(
      MplsLabelInstruction instruction, Configuration nextHop) {
    try {
      return Optional.of(instruction.resolveForNextHop(nextHop));
    } catch (IllegalArgumentException e) {
      return Optional.empty();
    }
  }

  private static final class State {
    private final List<SrSidValue> _labels;
    private final List<SymbolicNextHopBranch> _nextHopDecisions;
    private final RouteGuard _guard;

    private State(
        List<SrSidValue> labels, List<SymbolicNextHopBranch> nextHopDecisions, RouteGuard guard) {
      _labels = new ArrayList<>(labels);
      _nextHopDecisions = new ArrayList<>(nextHopDecisions);
      _guard = requireNonNull(guard);
    }
  }
}
