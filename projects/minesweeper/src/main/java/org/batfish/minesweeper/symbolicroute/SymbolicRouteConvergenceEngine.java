package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Queue;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Network-level FIFO convergence loop for guarded route advertisements. */
public final class SymbolicRouteConvergenceEngine<R extends AbstractRouteDecorator> {

  /** Advertisement or withdrawal owned and scheduled exclusively by this engine. */
  private static final class WorkItem<R extends AbstractRouteDecorator> {

    private enum Type {
      ADVERTISE,
      WITHDRAW
    }

    @Nonnull private final Type _type;
    @Nullable private final SymbolicRouteMessage<R> _message;
    @Nullable private final SymbolicRouteContributionId _withdrawal;
    @Nullable private final RouteGuard _expectedGuard;

    private WorkItem(
        Type type,
        @Nullable SymbolicRouteMessage<R> message,
        @Nullable SymbolicRouteContributionId withdrawal,
        @Nullable RouteGuard expectedGuard) {
      _type = requireNonNull(type, "type must be provided");
      _message = message;
      _withdrawal = withdrawal;
      _expectedGuard = expectedGuard;
    }

    private static <R extends AbstractRouteDecorator> WorkItem<R> advertise(
        SymbolicRouteMessage<R> message) {
      return new WorkItem<>(Type.ADVERTISE, requireNonNull(message), null, null);
    }

    private static <R extends AbstractRouteDecorator> WorkItem<R> withdraw(
        SymbolicRouteContributionId withdrawal, RouteGuard expectedGuard) {
      return new WorkItem<>(
          Type.WITHDRAW, null, requireNonNull(withdrawal), requireNonNull(expectedGuard));
    }

    @Nonnull
    private SymbolicRouteMessage<R> getMessage() {
      if (_message == null) {
        throw new IllegalStateException("withdrawal has no advertisement message");
      }
      return _message;
    }

    @Nonnull
    private SymbolicRouteContributionId getWithdrawal() {
      if (_withdrawal == null) {
        throw new IllegalStateException("advertisement has no withdrawal identity");
      }
      return _withdrawal;
    }

    @Nonnull
    private RouteGuard getExpectedGuard() {
      if (_expectedGuard == null) {
        throw new IllegalStateException("advertisement has no withdrawal guard");
      }
      return _expectedGuard;
    }
  }

  @Nonnull private final Map<String, SymbolicRouteIngressProcessor<R>> _ingressProcessors;
  @Nonnull private final Map<String, List<SymbolicRouteExporter<R>>> _exporters;
  @Nonnull private final List<Runnable> _stableStateListeners;

  @Nonnull
  private final Map<SymbolicRouteContributionId, ContributionLocation> _contributionLocations;

  @Nonnull
  private final Map<
          SymbolicRouteExporter<R>,
          Map<SymbolicRouteKey, Map<SymbolicRouteContributionId, AdvertisementRecord>>>
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
    _stableStateListeners = new ArrayList<>();
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
    Queue<WorkItem<R>> queue = new ArrayDeque<>();
    initialAdvertisements.forEach(message -> queue.add(WorkItem.advertise(message)));
    return run(queue);
  }

  /** Withdraws existing contributions and processes every resulting descendant update. */
  public SymbolicRouteConvergenceResult withdraw(
      Iterable<SymbolicRouteContributionId> withdrawals) {
    requireNonNull(withdrawals, "withdrawals must be provided");
    Queue<WorkItem<R>> queue = new ArrayDeque<>();
    for (SymbolicRouteContributionId withdrawal : withdrawals) {
      ContributionLocation location = _contributionLocations.get(withdrawal);
      if (location != null) {
        queue.add(WorkItem.withdraw(withdrawal, location._guard));
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
    Queue<WorkItem<R>> queue = new ArrayDeque<>();
    queue.add(WorkItem.withdraw(oldContribution, oldLocation._guard));
    queue.add(WorkItem.advertise(replacementAdvertisement));
    return run(queue);
  }

  /** Registers a synchronous callback invoked after this engine drains its global work queue. */
  public void addStableStateListener(Runnable listener) {
    Runnable checked = requireNonNull(listener, "listener must be provided");
    if (_stableStateListeners.contains(checked)) {
      throw new IllegalArgumentException("stable-state listener is already registered");
    }
    _stableStateListeners.add(checked);
  }

  private SymbolicRouteConvergenceResult run(Queue<WorkItem<R>> queue) {
    int processedMessages = 0;
    int processedWithdrawals = 0;
    int ribUpdates = 0;
    while (!queue.isEmpty()) {
      WorkItem<R> item = queue.remove();
      if (item._type == WorkItem.Type.WITHDRAW) {
        processedWithdrawals++;
        ribUpdates += processWithdrawal(item, queue);
        continue;
      }
      processedMessages++;
      ribUpdates += processAdvertisement(item.getMessage(), queue);
    }
    _stableStateListeners.forEach(Runnable::run);
    return new SymbolicRouteConvergenceResult(processedMessages, processedWithdrawals, ribUpdates);
  }

  private int processAdvertisement(SymbolicRouteMessage<R> message, Queue<WorkItem<R>> queue) {
    SymbolicRouteIngressProcessor<R> processor = _ingressProcessors.get(message.getReceiver());
    if (processor == null) {
      throw new IllegalArgumentException("no ingress processor for message receiver");
    }
    SymbolicRouteContributionId contributionId =
        new SymbolicRouteContributionId(
            message.getMessageId(), message.getSender(), message.getReceiver());
    java.util.Optional<SymbolicRouteIngressProcessor.PreparedCandidate<R>> prepared =
        processor.prepare(message);
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

  private int processWithdrawal(WorkItem<R> item, Queue<WorkItem<R>> queue) {
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
      Queue<WorkItem<R>> queue) {
    _contributionLocations.remove(contributionId);
    SymbolicRouteIngressProcessor<R> processor = _ingressProcessors.get(location._receiver);
    GuardedRibDelta<R> delta = processor.getRib().removeContribution(location._key, contributionId);
    return propagateDelta(processor, delta, queue);
  }

  private int propagateDelta(
      SymbolicRouteIngressProcessor<R> processor,
      GuardedRibDelta<R> delta,
      Queue<WorkItem<R>> queue) {
    int updates = 0;
    for (GuardedRibUpdate<R> update : delta.getUpdates()) {
      updates++;
      GuardedRibEntry<R> referenceEntry =
          update.getNewEntry() != null ? update.getNewEntry() : update.getOldEntry();
      SymbolicRouteKey key = referenceEntry.getSymbolicRoute().getKey();
      for (SymbolicRouteExporter<R> exporter :
          _exporters.getOrDefault(processor.getReceiver(), java.util.Collections.emptyList())) {
        Map<SymbolicRouteKey, Map<SymbolicRouteContributionId, AdvertisementRecord>> byCandidate =
            _advertisements.get(exporter);
        Map<SymbolicRouteContributionId, AdvertisementRecord> oldAdvertisements =
            byCandidate.remove(key);
        if (oldAdvertisements != null) {
          for (AdvertisementRecord oldAdvertisement : oldAdvertisements.values()) {
            exporter.removeDependencies(oldAdvertisement._id);
            queue.add(WorkItem.withdraw(oldAdvertisement._id, oldAdvertisement._guard));
          }
        }
        if (update.getNewEntry() == null) {
          continue;
        }
        Map<SymbolicRouteContributionId, AdvertisementRecord> newAdvertisements =
            new LinkedHashMap<>();
        for (Map.Entry<SymbolicRouteContributionId, GuardedRibEntry<R>> contribution :
            processor.getRib().getContributionEntries(key).entrySet()) {
          java.util.Optional<SymbolicRouteMessage<R>> child =
              exporter.export(contribution.getValue(), contribution.getKey());
          if (child.isPresent()) {
            SymbolicRouteMessage<R> message = child.get();
            SymbolicRouteContributionId childId =
                new SymbolicRouteContributionId(
                    message.getMessageId(), message.getSender(), message.getReceiver());
            newAdvertisements.put(
                contribution.getKey(), new AdvertisementRecord(childId, message.getGuard()));
            queue.add(WorkItem.advertise(message));
          }
        }
        if (!newAdvertisements.isEmpty()) {
          byCandidate.put(key, newAdvertisements);
        }
      }
    }
    return updates;
  }
}
