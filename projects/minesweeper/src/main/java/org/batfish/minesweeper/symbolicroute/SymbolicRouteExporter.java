package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/** Hoyan Algorithm 1 lines 17-22: egress policy, link guard, advertisement, and dependency. */
public final class SymbolicRouteExporter<R extends AbstractRouteDecorator> {

  @Nonnull private final String _sender;
  @Nonnull private final String _receiver;
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
    _sender = requireNonNull(sender, "sender must be provided");
    _receiver = requireNonNull(receiver, "receiver must be provided");
    _linkGuard = requireNonNull(linkGuard, "linkGuard must be provided");
    _egressPolicy = requireNonNull(egressPolicy, "egressPolicy must be provided");
    _messageIdFactory = requireNonNull(messageIdFactory, "messageIdFactory must be provided");
    _dependencies = requireNonNull(dependencies, "dependencies must be provided");
  }

  /** Exports one selected RIB entry to this peer, if policy and guard permit it. */
  public Optional<SymbolicRouteMessage<R>> export(
      GuardedRibEntry<R> entry, Iterable<SymbolicRouteContributionId> parents) {
    requireNonNull(entry, "entry must be provided");
    requireNonNull(parents, "parents must be provided");
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
    List<SymbolicRouteContributionId> parentList = new ArrayList<>();
    parents.forEach(parentList::add);
    String messageId =
        requireNonNull(
            _messageIdFactory.create(_sender, _receiver, exportedRoute.get()),
            "messageIdFactory returned null");
    SymbolicRouteContributionId child =
        new SymbolicRouteContributionId(messageId, _sender, _receiver);
    _dependencies.replaceParents(child, parentList);
    SymbolicRouteProvenance oldProvenance = symbolicRoute.getProvenance();
    List<String> path = new ArrayList<>(oldProvenance.getRouterPath());
    path.add(_receiver);
    String soleParentMessageId = parentList.size() == 1 ? parentList.get(0).getMessageId() : null;
    SymbolicRouteProvenance provenance =
        new SymbolicRouteProvenance(
            oldProvenance.getOriginRouter(),
            _receiver,
            _sender,
            null,
            ImmutableList.copyOf(path),
            soleParentMessageId);
    return Optional.of(
        new SymbolicRouteMessage<>(
            messageId,
            _sender,
            _receiver,
            SymbolicRouteMessage.Stage.INGRESS,
            exportedRoute.get(),
            messageGuard,
            provenance));
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
