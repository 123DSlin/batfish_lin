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
      if (message.getStage() != SymbolicRouteMessage.Stage.INGRESS) {
        throw new IllegalArgumentException("ingress processor accepts only INGRESS messages");
      }
      if (!message.getReceiver().equals(_receiver)) {
        throw new IllegalArgumentException("message receiver does not match the processor RIB");
      }
      Optional<R> acceptedRoute =
          requireNonNull(_ingressPolicy.process(message), "ingress policy returned null");
      if (!acceptedRoute.isPresent()) {
        continue;
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
      GuardedRibDelta<R> delta =
          _rib.putContribution(
              new SymbolicRouteContributionId(
                  message.getMessageId(), message.getSender(), message.getReceiver()),
              candidate);
      if (!delta.isEmpty()) {
        deltas.add(delta);
      }
    }
    return ImmutableList.copyOf(deltas);
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
