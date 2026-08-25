package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Queue;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Network-level FIFO convergence loop for guarded route advertisements. */
public final class SymbolicRouteConvergenceEngine<R extends AbstractRouteDecorator> {

  @Nonnull private final Map<String, SymbolicRouteIngressProcessor<R>> _ingressProcessors;
  @Nonnull private final Map<String, List<SymbolicRouteExporter<R>>> _exporters;

  public SymbolicRouteConvergenceEngine(
      Iterable<SymbolicRouteIngressProcessor<R>> ingressProcessors,
      Iterable<SymbolicRouteExporter<R>> exporters) {
    _ingressProcessors = new LinkedHashMap<>();
    for (SymbolicRouteIngressProcessor<R> processor : ingressProcessors) {
      SymbolicRouteIngressProcessor<R> old =
          _ingressProcessors.put(processor.getReceiver(), processor);
      if (old != null) {
        throw new IllegalArgumentException("duplicate ingress processor for one receiver");
      }
    }
    _exporters = new LinkedHashMap<>();
    for (SymbolicRouteExporter<R> exporter : exporters) {
      if (!_ingressProcessors.containsKey(exporter.getSender())
          || !_ingressProcessors.containsKey(exporter.getReceiver())) {
        throw new IllegalArgumentException("exporter endpoints must have ingress processors");
      }
      _exporters.computeIfAbsent(exporter.getSender(), unused -> new ArrayList<>()).add(exporter);
    }
  }

  /** Runs until the work queue is empty. Non-monotonic withdrawal is deliberately rejected. */
  public SymbolicRouteConvergenceResult converge(
      Iterable<SymbolicRouteMessage<R>> initialAdvertisements) {
    requireNonNull(initialAdvertisements, "initialAdvertisements must be provided");
    Queue<SymbolicRouteMessage<R>> queue = new ArrayDeque<>();
    initialAdvertisements.forEach(queue::add);
    int processedMessages = 0;
    int ribUpdates = 0;
    while (!queue.isEmpty()) {
      SymbolicRouteMessage<R> message = queue.remove();
      SymbolicRouteIngressProcessor<R> processor = _ingressProcessors.get(message.getReceiver());
      if (processor == null) {
        throw new IllegalArgumentException("no ingress processor for message receiver");
      }
      processedMessages++;
      List<GuardedRibDelta<R>> deltas =
          processor.process(java.util.Collections.singletonList(message));
      for (GuardedRibDelta<R> delta : deltas) {
        for (GuardedRibUpdate<R> update : delta.getUpdates()) {
          ribUpdates++;
          GuardedRibEntry<R> newEntry = update.getNewEntry();
          if (newEntry == null) {
            throw new UnsupportedOperationException(
                "route removal requires recursive withdrawal support");
          }
          Iterable<SymbolicRouteContributionId> parents =
              processor.getRib().getContributionIds(newEntry.getSymbolicRoute().getKey());
          for (SymbolicRouteExporter<R> exporter :
              _exporters.getOrDefault(message.getReceiver(), java.util.Collections.emptyList())) {
            Optional<SymbolicRouteMessage<R>> child = exporter.export(newEntry, parents);
            if (child.isPresent()) {
              queue.add(child.get());
            } else if (update.getOldEntry() != null
                && update.getOldEntry().getSelectionGuard().isSatisfiable()) {
              throw new UnsupportedOperationException(
                  "removing a previous advertisement requires recursive withdrawal support");
            }
          }
        }
      }
    }
    return new SymbolicRouteConvergenceResult(processedMessages, ribUpdates);
  }
}
