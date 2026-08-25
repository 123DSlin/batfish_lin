package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Hoyan Algorithm 1 lines 2-10: initialization, work queue, ingress policy, and RIB update. */
public final class SymbolicRouteIngressProcessor<R extends AbstractRouteDecorator> {

  @Nonnull private final String _receiver;
  @Nonnull private final GuardedRib<R> _rib;
  @Nonnull private final SymbolicRouteIngressPolicy<R> _ingressPolicy;
  @Nonnull private final SymbolicRouteKeyFactory<R> _keyFactory;
  @Nonnull private final SymbolicRouteWorkQueue<R> _workQueue;

  public SymbolicRouteIngressProcessor(
      String receiver,
      GuardedRib<R> rib,
      SymbolicRouteIngressPolicy<R> ingressPolicy,
      SymbolicRouteKeyFactory<R> keyFactory) {
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _rib = requireNonNull(rib, "rib must be provided");
    _ingressPolicy = requireNonNull(ingressPolicy, "ingressPolicy must be provided");
    _keyFactory = requireNonNull(keyFactory, "keyFactory must be provided");
    _workQueue = new SymbolicRouteWorkQueue<>();
  }

  /** Processes the supplied initial advertisements until the ingress work queue is empty. */
  public ImmutableList<GuardedRibDelta<R>> process(
      Iterable<SymbolicRouteMessage<R>> initialAdvertisements) {
    requireNonNull(initialAdvertisements, "initialAdvertisements must be provided");
    for (SymbolicRouteMessage<R> message : initialAdvertisements) {
      _workQueue.enqueue(message);
    }
    List<GuardedRibDelta<R>> deltas = new ArrayList<>();
    SymbolicRouteMessage<R> message;
    while ((message = _workQueue.poll()) != null) {
      processMessage(message)
          .map(SymbolicRouteIngressResult::getDelta)
          .filter(delta -> !delta.isEmpty())
          .ifPresent(deltas::add);
    }
    return ImmutableList.copyOf(deltas);
  }

  /** Processes one message and returns empty only when ingress policy denies it. */
  public Optional<SymbolicRouteIngressResult<R>> processMessage(SymbolicRouteMessage<R> message) {
    return prepare(message).map(this::install);
  }

  /**
   * Applies ingress policy without modifying the RIB, so callers can validate candidate identity.
   */
  Optional<SymbolicRouteIngressCandidate<R>> prepare(SymbolicRouteMessage<R> message) {
    requireNonNull(message, "message must be provided");
    if (message.getStage() != SymbolicRouteMessage.Stage.INGRESS) {
      throw new IllegalArgumentException("ingress processor accepts only INGRESS messages");
    }
    if (!message.getReceiver().equals(_receiver)) {
      throw new IllegalArgumentException("message receiver does not match the processor RIB");
    }
    Optional<R> acceptedRoute =
        requireNonNull(_ingressPolicy.process(message), "ingress policy returned null");
    if (!acceptedRoute.isPresent()) {
      return Optional.empty();
    }
    R route = acceptedRoute.get();
    SymbolicRouteKey key =
        requireNonNull(
            _keyFactory.create(message.getReceiver(), route), "key factory returned null");
    if (!key.getRouter().equals(_receiver)) {
      throw new IllegalArgumentException("key factory returned a key for a different router");
    }
    SymbolicRoute<R> candidate =
        new SymbolicRoute<>(key, route, message.getGuard(), message.getProvenance());
    return Optional.of(
        new SymbolicRouteIngressCandidate<>(
            new SymbolicRouteContributionId(
                message.getMessageId(), message.getSender(), message.getReceiver()),
            candidate));
  }

  /** Installs a previously prepared ingress candidate. */
  SymbolicRouteIngressResult<R> install(SymbolicRouteIngressCandidate<R> prepared) {
    requireNonNull(prepared, "prepared candidate must be provided");
    SymbolicRoute<R> candidate = prepared.getCandidate();
    GuardedRibDelta<R> delta = _rib.putContribution(prepared.getContributionId(), candidate);
    return new SymbolicRouteIngressResult<>(candidate.getKey(), delta);
  }

  public boolean isQueueEmpty() {
    return _workQueue.isEmpty();
  }

  @Nonnull
  public String getReceiver() {
    return _receiver;
  }

  @Nonnull
  public GuardedRib<R> getRib() {
    return _rib;
  }
}
