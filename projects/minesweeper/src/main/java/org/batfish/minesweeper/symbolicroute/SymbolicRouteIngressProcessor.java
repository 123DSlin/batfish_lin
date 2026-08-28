package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Hoyan Algorithm 1 ingress-policy and guarded-RIB installation steps. */
public final class SymbolicRouteIngressProcessor<R extends AbstractRouteDecorator> {

  /** Import-policy result prepared for identity validation before installation. */
  static final class PreparedCandidate<R extends AbstractRouteDecorator> {

    @Nonnull private final SymbolicRouteContributionId _contributionId;
    @Nonnull private final SymbolicRoute<R> _candidate;

    PreparedCandidate(
        SymbolicRouteContributionId contributionId, SymbolicRoute<R> candidate) {
      _contributionId = requireNonNull(contributionId, "contributionId must be provided");
      _candidate = requireNonNull(candidate, "candidate must be provided");
    }

    @Nonnull
    SymbolicRouteContributionId getContributionId() {
      return _contributionId;
    }

    @Nonnull
    SymbolicRoute<R> getCandidate() {
      return _candidate;
    }
  }

  @Nonnull private final String _receiver;
  @Nonnull private final GuardedRib<R> _rib;
  @Nonnull private final SymbolicRouteIngressPolicy<R> _ingressPolicy;
  @Nonnull private final SymbolicRouteKeyFactory<R> _keyFactory;

  public SymbolicRouteIngressProcessor(
      String receiver,
      GuardedRib<R> rib,
      SymbolicRouteIngressPolicy<R> ingressPolicy,
      SymbolicRouteKeyFactory<R> keyFactory) {
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _rib = requireNonNull(rib, "rib must be provided");
    _ingressPolicy = requireNonNull(ingressPolicy, "ingressPolicy must be provided");
    _keyFactory = requireNonNull(keyFactory, "keyFactory must be provided");
  }

  /** Processes one message and returns empty only when ingress policy denies it. */
  public Optional<SymbolicRouteIngressResult<R>> processMessage(SymbolicRouteMessage<R> message) {
    return prepare(message).map(this::install);
  }

  /**
   * Applies ingress policy without modifying the RIB, so callers can validate candidate identity.
   */
  Optional<PreparedCandidate<R>> prepare(SymbolicRouteMessage<R> message) {
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
        new PreparedCandidate<>(
            new SymbolicRouteContributionId(
                message.getMessageId(), message.getSender(), message.getReceiver()),
            candidate));
  }

  /** Installs a previously prepared ingress candidate. */
  SymbolicRouteIngressResult<R> install(PreparedCandidate<R> prepared) {
    requireNonNull(prepared, "prepared candidate must be provided");
    SymbolicRoute<R> candidate = prepared.getCandidate();
    GuardedRibDelta<R> delta = _rib.putContribution(prepared.getContributionId(), candidate);
    return new SymbolicRouteIngressResult<>(candidate.getKey(), delta);
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
