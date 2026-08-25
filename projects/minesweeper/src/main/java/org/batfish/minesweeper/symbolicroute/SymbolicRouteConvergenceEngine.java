package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Network-level FIFO convergence loop for guarded route advertisements. */
public final class SymbolicRouteConvergenceEngine<R extends AbstractRouteDecorator> {

  @Nonnull private final Map<String, SymbolicRouteIngressProcessor<R>> _ingressProcessors;
  @Nonnull private final Map<String, List<SymbolicRouteExporter<R>>> _exporters;

  @Nonnull
  private final Map<SymbolicRouteContributionId, ContributionLocation> _contributionLocations;

  @Nonnull
  private final Map<SymbolicRouteExporter<R>, Map<SymbolicRouteKey, AdvertisementRecord>>
      _advertisements;

  private static final class ContributionLocation {
    private final String _receiver;
    private final SymbolicRouteKey _key;
    private final RouteGuard _guard;

    private ContributionLocation(String receiver, SymbolicRouteKey key, RouteGuard guard) {
      _receiver = receiver;
      _key = key;
      _guard = guard;
    }
  }

  private static final class AdvertisementRecord {
    private final SymbolicRouteContributionId _id;
    private final RouteGuard _guard;

    private AdvertisementRecord(SymbolicRouteContributionId id, RouteGuard guard) {
      _id = id;
      _guard = guard;
    }
  }

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
    _contributionLocations = new LinkedHashMap<>();
    _advertisements = new LinkedHashMap<>();
    for (SymbolicRouteExporter<R> exporter : exporters) {
      if (!_ingressProcessors.containsKey(exporter.getSender())
          || !_ingressProcessors.containsKey(exporter.getReceiver())) {
        throw new IllegalArgumentException("exporter endpoints must have ingress processors");
      }
      _exporters.computeIfAbsent(exporter.getSender(), unused -> new ArrayList<>()).add(exporter);
      _advertisements.put(exporter, new LinkedHashMap<>());
    }
  }

  /** Runs advertisements and all recursively generated withdrawals until the queue is empty. */
  public SymbolicRouteConvergenceResult converge(
      Iterable<SymbolicRouteMessage<R>> initialAdvertisements) {
    requireNonNull(initialAdvertisements, "initialAdvertisements must be provided");
    Queue<SymbolicRouteWorkItem<R>> queue = new ArrayDeque<>();
    initialAdvertisements.forEach(message -> queue.add(SymbolicRouteWorkItem.advertise(message)));
    return run(queue);
  }

  /** Withdraws existing contributions and processes every resulting descendant update. */
  public SymbolicRouteConvergenceResult withdraw(
      Iterable<SymbolicRouteContributionId> withdrawals) {
    requireNonNull(withdrawals, "withdrawals must be provided");
    Queue<SymbolicRouteWorkItem<R>> queue = new ArrayDeque<>();
    for (SymbolicRouteContributionId withdrawal : withdrawals) {
      ContributionLocation location = _contributionLocations.get(withdrawal);
      if (location != null) {
        queue.add(SymbolicRouteWorkItem.withdraw(withdrawal, location._guard));
      }
    }
    return run(queue);
  }

  /** Atomically withdraws one contribution and advertises its replacement under a new identity. */
  public SymbolicRouteConvergenceResult replace(
      SymbolicRouteContributionId oldContribution,
      SymbolicRouteMessage<R> replacementAdvertisement) {
    requireNonNull(oldContribution, "oldContribution must be provided");
    requireNonNull(replacementAdvertisement, "replacementAdvertisement must be provided");
    SymbolicRouteContributionId replacementContribution =
        new SymbolicRouteContributionId(
            replacementAdvertisement.getMessageId(),
            replacementAdvertisement.getSender(),
            replacementAdvertisement.getReceiver());
    if (oldContribution.equals(replacementContribution)) {
      throw new IllegalArgumentException("route replacement requires a new contribution identity");
    }
    ContributionLocation oldLocation = _contributionLocations.get(oldContribution);
    if (oldLocation == null) {
      throw new IllegalArgumentException("route replacement requires an existing old contribution");
    }
    if (_contributionLocations.containsKey(replacementContribution)) {
      throw new IllegalArgumentException("route replacement requires an unused new identity");
    }
    Queue<SymbolicRouteWorkItem<R>> queue = new ArrayDeque<>();
    queue.add(SymbolicRouteWorkItem.withdraw(oldContribution, oldLocation._guard));
    queue.add(SymbolicRouteWorkItem.advertise(replacementAdvertisement));
    return run(queue);
  }

  private SymbolicRouteConvergenceResult run(Queue<SymbolicRouteWorkItem<R>> queue) {
    int processedMessages = 0;
    int processedWithdrawals = 0;
    int ribUpdates = 0;
    while (!queue.isEmpty()) {
      SymbolicRouteWorkItem<R> item = queue.remove();
      if (item.getType() == SymbolicRouteWorkItem.Type.WITHDRAW) {
        processedWithdrawals++;
        ribUpdates += processWithdrawal(item, queue);
        continue;
      }
      processedMessages++;
      ribUpdates += processAdvertisement(item.getMessage(), queue);
    }
    return new SymbolicRouteConvergenceResult(processedMessages, processedWithdrawals, ribUpdates);
  }

  private int processAdvertisement(
      SymbolicRouteMessage<R> message, Queue<SymbolicRouteWorkItem<R>> queue) {
    SymbolicRouteIngressProcessor<R> processor = _ingressProcessors.get(message.getReceiver());
    if (processor == null) {
      throw new IllegalArgumentException("no ingress processor for message receiver");
    }
    SymbolicRouteContributionId contributionId =
        new SymbolicRouteContributionId(
            message.getMessageId(), message.getSender(), message.getReceiver());
    java.util.Optional<SymbolicRouteIngressCandidate<R>> prepared = processor.prepare(message);
    if (!prepared.isPresent()) {
      ContributionLocation oldLocation = _contributionLocations.get(contributionId);
      return oldLocation == null ? 0 : removeContribution(contributionId, oldLocation, queue);
    }
    ContributionLocation oldLocation = _contributionLocations.get(contributionId);
    SymbolicRouteKey preparedKey = prepared.get().getCandidate().getKey();
    if (oldLocation != null && !oldLocation._key.equals(preparedKey)) {
      throw new IllegalArgumentException(
          "one contribution identity must deterministically map to one candidate key; use replace"
              + " with a new identity for a route replacement");
    }
    SymbolicRouteIngressResult<R> ingressResult = processor.install(prepared.get());
    _contributionLocations.put(
        contributionId,
        new ContributionLocation(
            message.getReceiver(), ingressResult.getKey(), message.getGuard()));
    return propagateDelta(processor, ingressResult.getDelta(), queue);
  }

  private int processWithdrawal(
      SymbolicRouteWorkItem<R> item, Queue<SymbolicRouteWorkItem<R>> queue) {
    SymbolicRouteContributionId contributionId = item.getWithdrawal();
    ContributionLocation location = _contributionLocations.get(contributionId);
    if (location == null || !location._guard.isEquivalentTo(item.getExpectedGuard())) {
      return 0;
    }
    return removeContribution(contributionId, location, queue);
  }

  private int removeContribution(
      SymbolicRouteContributionId contributionId,
      ContributionLocation location,
      Queue<SymbolicRouteWorkItem<R>> queue) {
    _contributionLocations.remove(contributionId);
    SymbolicRouteIngressProcessor<R> processor = _ingressProcessors.get(location._receiver);
    GuardedRibDelta<R> delta = processor.getRib().removeContribution(location._key, contributionId);
    return propagateDelta(processor, delta, queue);
  }

  private int propagateDelta(
      SymbolicRouteIngressProcessor<R> processor,
      GuardedRibDelta<R> delta,
      Queue<SymbolicRouteWorkItem<R>> queue) {
    int updates = 0;
    for (GuardedRibUpdate<R> update : delta.getUpdates()) {
      updates++;
      GuardedRibEntry<R> referenceEntry =
          update.getNewEntry() != null ? update.getNewEntry() : update.getOldEntry();
      SymbolicRouteKey key = referenceEntry.getSymbolicRoute().getKey();
      for (SymbolicRouteExporter<R> exporter :
          _exporters.getOrDefault(processor.getReceiver(), java.util.Collections.emptyList())) {
        Map<SymbolicRouteKey, AdvertisementRecord> byCandidate = _advertisements.get(exporter);
        AdvertisementRecord oldAdvertisement = byCandidate.remove(key);
        if (oldAdvertisement != null) {
          exporter.removeDependencies(oldAdvertisement._id);
          queue.add(SymbolicRouteWorkItem.withdraw(oldAdvertisement._id, oldAdvertisement._guard));
        }
        if (update.getNewEntry() == null) {
          continue;
        }
        Iterable<SymbolicRouteContributionId> parents = processor.getRib().getContributionIds(key);
        java.util.Optional<SymbolicRouteMessage<R>> child =
            exporter.export(update.getNewEntry(), parents);
        if (child.isPresent()) {
          SymbolicRouteMessage<R> message = child.get();
          SymbolicRouteContributionId childId =
              new SymbolicRouteContributionId(
                  message.getMessageId(), message.getSender(), message.getReceiver());
          byCandidate.put(key, new AdvertisementRecord(childId, message.getGuard()));
          queue.add(SymbolicRouteWorkItem.advertise(message));
        }
      }
    }
    return updates;
  }
}
