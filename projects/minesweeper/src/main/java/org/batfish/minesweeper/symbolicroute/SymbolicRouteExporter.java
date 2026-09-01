package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Hoyan Algorithm 1 lines 17-22: egress policy, link guard, advertisement, and dependency. */
public final class SymbolicRouteExporter<R extends AbstractRouteDecorator> {

  @Nonnull private final String _sender;
  @Nonnull private final String _receiver;
  @Nullable private final String _sessionId;
  @Nonnull private final RouteGuard _linkGuard;
  @Nonnull private final SymbolicRouteEgressPolicy<R> _egressPolicy;
  @Nonnull private final SymbolicRouteMessageIdFactory<R> _messageIdFactory;
  @Nonnull private final SymbolicRoutePropagationDependencies _dependencies;

  public SymbolicRouteExporter(
      String sender,
      String receiver,
      RouteGuard linkGuard,
      SymbolicRouteEgressPolicy<R> egressPolicy,
      SymbolicRouteMessageIdFactory<R> messageIdFactory,
      SymbolicRoutePropagationDependencies dependencies) {
    this(sender, receiver, null, linkGuard, egressPolicy, messageIdFactory, dependencies);
  }

  public SymbolicRouteExporter(
      String sender,
      String receiver,
      @Nullable String sessionId,
      RouteGuard linkGuard,
      SymbolicRouteEgressPolicy<R> egressPolicy,
      SymbolicRouteMessageIdFactory<R> messageIdFactory,
      SymbolicRoutePropagationDependencies dependencies) {
    _sender = requireNonNull(sender, "sender must be provided");
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _sessionId = sessionId;
    _linkGuard = requireNonNull(linkGuard, "linkGuard must be provided");
    _egressPolicy = requireNonNull(egressPolicy, "egressPolicy must be provided");
    _messageIdFactory = requireNonNull(messageIdFactory, "messageIdFactory must be provided");
    _dependencies = requireNonNull(dependencies, "dependencies must be provided");
  }

  /** Exports one selected contribution branch to this peer, if policy and guard permit it. */
  public Optional<SymbolicRouteMessage<R>> export(
      GuardedRibEntry<R> entry, SymbolicRouteContributionId parent) {
    requireNonNull(entry, "entry must be provided");
    requireNonNull(parent, "parent must be provided");
    SymbolicRoute<R> symbolicRoute = entry.getSymbolicRoute();
    if (!symbolicRoute.getKey().getRouter().equals(_sender)) {
      throw new IllegalArgumentException("RIB entry does not belong to exporter sender");
    }
    if (!symbolicRoute.getProvenance().getCurrentRouter().equals(_sender)) {
      throw new IllegalArgumentException("route provenance is not at exporter sender");
    }
    Optional<R> exportedRoute =
        requireNonNull(
            _egressPolicy.process(_sender, _receiver, symbolicRoute.getRoute()),
            "egress policy returned null");
    if (!exportedRoute.isPresent()) {
      return Optional.empty();
    }
    RouteGuard messageGuard = entry.getSelectionGuard().and(_linkGuard).simplify();
    if (!messageGuard.isSatisfiable()) {
      return Optional.empty();
    }
    String baseMessageId =
        requireNonNull(
            _messageIdFactory.create(
                _sender, _receiver, symbolicRoute.getKey(), exportedRoute.get()),
            "messageIdFactory returned null");
    String messageId = branchMessageId(baseMessageId, parent);
    SymbolicRouteContributionId child =
        new SymbolicRouteContributionId(messageId, _sender, _receiver);
    _dependencies.replaceParents(child, java.util.Collections.singleton(parent));
    SymbolicRouteProvenance oldProvenance = symbolicRoute.getProvenance();
    List<String> path = new ArrayList<>(oldProvenance.getRouterPath());
    path.add(_receiver);
    SymbolicRouteProvenance provenance =
        new SymbolicRouteProvenance(
            oldProvenance.getOriginRouter(),
            _receiver,
            _sender,
            null,
            com.google.common.collect.ImmutableList.copyOf(path),
            parent.getMessageId());
    return Optional.of(
        new SymbolicRouteMessage<>(
            messageId,
            _sender,
            _receiver,
            _sessionId,
            SymbolicRouteMessage.Stage.INGRESS,
            exportedRoute.get(),
            messageGuard,
            provenance));
  }

  private static String branchMessageId(String baseMessageId, SymbolicRouteContributionId parent) {
    return String.format(
        "%d:%s:%d:%s:%d:%s:%s",
        baseMessageId.length(),
        baseMessageId,
        parent.getSender().length(),
        parent.getSender(),
        parent.getReceiver().length(),
        parent.getReceiver(),
        parent.getMessageId());
  }

  @Nonnull
  public String getSender() {
    return _sender;
  }

  @Nonnull
  public String getReceiver() {
    return _receiver;
  }

  public void removeDependencies(SymbolicRouteContributionId child) {
    _dependencies.removeChild(child);
  }
}
