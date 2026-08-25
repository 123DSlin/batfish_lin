package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.bgp.AddressFamily.Type.IPV4_UNICAST;
import static org.batfish.datamodel.routing_policy.Environment.Direction.IN;
import static org.batfish.datamodel.routing_policy.Environment.Direction.OUT;
import static org.batfish.dataplane.protocols.BgpProtocolHelper.transformBgpRouteOnImport;
import static org.batfish.dataplane.protocols.BgpProtocolHelper.transformBgpRoutePostExport;
import static org.batfish.dataplane.protocols.BgpProtocolHelper.transformBgpRoutePreExport;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpTieBreaker;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.bgp.AddressFamily;
import org.batfish.datamodel.routing_policy.RoutingPolicy;
import org.batfish.dataplane.rib.Bgpv4Rib;

/** IPv4-unicast BGP adapter delegating transformations, policies, and preference to Batfish. */
public final class BatfishBgpProtocolAdapter
    implements SymbolicRouteProtocolAdapter<AnnotatedRoute<Bgpv4Route>> {

  @Nonnull private final Map<String, BatfishBgpEdge> _edges;
  @Nonnull private final Bgpv4Rib _preferenceOracle;

  public BatfishBgpProtocolAdapter(Iterable<BatfishBgpEdge> edges) {
    _edges = new LinkedHashMap<>();
    for (BatfishBgpEdge edge : requireNonNull(edges, "edges must be provided")) {
      if (_edges.put(edge.getSessionId(), edge) != null) {
        throw new IllegalArgumentException("duplicate BGP edge session identity");
      }
    }
    _preferenceOracle = new Bgpv4Rib(null, BgpTieBreaker.ROUTER_ID, 1, null, false, false);
  }

  @Override
  public Comparator<AnnotatedRoute<Bgpv4Route>> preferenceComparator(String receiver) {
    return (left, right) ->
        -Integer.signum(_preferenceOracle.comparePreference(left.getRoute(), right.getRoute()));
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<Bgpv4Route>> processImport(
      SymbolicRouteMessage<AnnotatedRoute<Bgpv4Route>> message) {
    if (message.getSessionId() == null) {
      return Optional.of(message.getRoute());
    }
    BatfishBgpEdge edge = edge(message.getSessionId());
    if (!message.getSender().equals(edge.getSenderConfiguration().getHostname())
        || !message.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
      throw new IllegalArgumentException("BGP message endpoints do not match session edge");
    }
    Bgpv4Route.Builder imported =
        transformBgpRouteOnImport(
            message.getRoute().getRoute(),
            edge.getImportSessionProperties().getHeadAs(),
            edge.getAllowLocalAsIn(),
            edge.getImportSessionProperties().isEbgp(),
            edge.getReceiverProcess(),
            edge.getReceiverPeerIp(),
            edge.getReceiverPeerInterface());
    if (imported == null) {
      return Optional.empty();
    }
    Bgpv4Route transformed = imported.build();
    AddressFamily receiverAf = edge.getReceiverPeer().getAddressFamily(IPV4_UNICAST);
    if (receiverAf == null || receiverAf.getImportPolicy() == null) {
      return Optional.of(new AnnotatedRoute<>(transformed, edge.getReceiverVrf()));
    }
    RoutingPolicy policy =
        edge.getReceiverConfiguration().getRoutingPolicies().get(receiverAf.getImportPolicy());
    if (policy == null) {
      return Optional.empty();
    }
    Bgpv4Route.Builder policyOutput = transformed.toBuilder();
    return policy.processBgpRoute(transformed, policyOutput, edge.getImportSessionProperties(), IN)
        ? Optional.of(new AnnotatedRoute<>(policyOutput.build(), edge.getReceiverVrf()))
        : Optional.empty();
  }

  @Override
  @Nonnull
  public SymbolicRouteKey createCandidateKey(
      String receiver, AnnotatedRoute<Bgpv4Route> importedRoute) {
    return new SymbolicRouteKey(receiver, importedRoute.getSourceVrf(), importedRoute);
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<Bgpv4Route>> processExport(
      SymbolicRouteSession session, AnnotatedRoute<Bgpv4Route> selectedRoute) {
    BatfishBgpEdge edge = edge(session.getSessionId());
    if (!session.getSender().equals(edge.getSenderConfiguration().getHostname())
        || !session.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
      throw new IllegalArgumentException("BGP session endpoints do not match session edge");
    }
    if (!selectedRoute.getSourceVrf().equals(edge.getSenderVrf())) {
      return Optional.empty();
    }
    Bgpv4Route.Builder output =
        transformBgpRoutePreExport(
            edge.getSenderPeer(),
            edge.getReceiverPeer(),
            edge.getExportSessionProperties(),
            edge.getSenderProcess(),
            edge.getReceiverProcess(),
            selectedRoute.getRoute(),
            IPV4_UNICAST);
    if (output == null) {
      return Optional.empty();
    }
    AddressFamily senderAf = edge.getSenderPeer().getAddressFamily(IPV4_UNICAST);
    if (senderAf == null || senderAf.getExportPolicy() == null) {
      return Optional.empty();
    }
    RoutingPolicy policy =
        edge.getSenderConfiguration().getRoutingPolicies().get(senderAf.getExportPolicy());
    if (policy == null
        || !policy.processBgpRoute(selectedRoute, output, edge.getExportSessionProperties(), OUT)) {
      return Optional.empty();
    }
    transformBgpRoutePostExport(
        output,
        edge.getExportSessionProperties().isEbgp(),
        edge.getExportSessionProperties().getConfedSessionType(),
        edge.getExportSessionProperties().getHeadAs(),
        edge.getExportSessionProperties().getHeadIp(),
        selectedRoute.getRoute().getNextHopIp());
    return Optional.of(new AnnotatedRoute<>(output.build(), edge.getReceiverVrf()));
  }

  @Override
  @Nonnull
  public String createExportMessageId(
      SymbolicRouteSession session, AnnotatedRoute<Bgpv4Route> exportedRoute) {
    return exportedRoute.toString();
  }

  private BatfishBgpEdge edge(String sessionId) {
    BatfishBgpEdge edge = _edges.get(sessionId);
    if (edge == null) {
      throw new IllegalArgumentException("unknown BGP edge session identity");
    }
    return edge;
  }
}
