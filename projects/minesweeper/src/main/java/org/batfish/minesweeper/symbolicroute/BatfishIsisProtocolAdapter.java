package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.IsisRoute.DEFAULT_METRIC;
import static org.batfish.datamodel.isis.IsisInterfaceMode.ACTIVE;
import static org.batfish.datamodel.isis.IsisLevel.LEVEL_1;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.dataplane.rib.IsisRib;

/** HoYAN Algorithm 2 adapter for parser-derived IPv4 IS-IS Level-1 point-to-point circuits. */
public final class BatfishIsisProtocolAdapter
    implements SymbolicRouteProtocolAdapter<AnnotatedRoute<IsisRoute>> {

  @Nonnull private final Map<String, BatfishIsisEdge> _edges;
  @Nonnull private final Map<String, Map<SymbolicRouteKey, String>> _exportIdentities;
  @Nonnull private final Map<String, Map<SymbolicRouteKey, AnnotatedRoute<IsisRoute>>> _exports;

  public BatfishIsisProtocolAdapter(Iterable<BatfishIsisEdge> edges) {
    _edges = new LinkedHashMap<>();
    _exportIdentities = new LinkedHashMap<>();
    _exports = new LinkedHashMap<>();
    for (BatfishIsisEdge edge : requireNonNull(edges, "edges must be provided")) {
      if (!edge.getEdge().getCircuitType().includes(LEVEL_1)) {
        throw new IllegalArgumentException("initial IS-IS adapter supports only Level-1 circuits");
      }
      if (_edges.put(edge.getSessionId(), edge) != null) {
        throw new IllegalArgumentException("duplicate IS-IS edge session identity");
      }
      requireActiveLevel1(edge.getSenderInterface());
      requireActiveLevel1(edge.getReceiverInterface());
      _exportIdentities.put(edge.getSessionId(), new LinkedHashMap<>());
      _exports.put(edge.getSessionId(), new LinkedHashMap<>());
    }
  }

  @Override
  public Comparator<AnnotatedRoute<IsisRoute>> preferenceComparator(String receiver) {
    return (left, right) ->
        -Integer.signum(
            IsisRib.routePreferenceComparator.compare(left.getRoute(), right.getRoute()));
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<IsisRoute>> processImport(
      SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> message) {
    if (message.getSessionId() == null) {
      return message.getRoute().getRoute().getLevel() == LEVEL_1
          ? Optional.of(message.getRoute())
          : Optional.empty();
    }
    BatfishIsisEdge edge = edge(message.getSessionId());
    validateEndpoints(message, edge);
    long receiverOccurrences =
        message.getProvenance().getRouterPath().stream()
            .filter(message.getReceiver()::equals)
            .count();
    if (receiverOccurrences > 1) {
      return Optional.empty();
    }
    IsisRoute neighborRoute = message.getRoute().getRoute();
    if (neighborRoute.getLevel() != LEVEL_1) {
      return Optional.empty();
    }
    IsisInterfaceLevelSettings settings = edge.getReceiverInterface().getIsis().getLevel1();
    long incrementalMetric = firstNonNull(settings.getCost(), DEFAULT_METRIC);
    ConcreteInterfaceAddress senderAddress = edge.getSenderInterface().getConcreteAddress();
    if (senderAddress == null) {
      throw new IllegalArgumentException("numbered IS-IS point-to-point interface is required");
    }
    IsisRoute imported =
        neighborRoute.toBuilder()
            .setAdmin(
                neighborRoute
                    .getProtocol()
                    .getDefaultAdministrativeCost(
                        edge.getReceiverConfiguration().getConfigurationFormat()))
            .setMetric(neighborRoute.getMetric() + incrementalMetric)
            .setNextHopIp(senderAddress.getIp())
            .setNonRouting(false)
            .build();
    return Optional.of(new AnnotatedRoute<>(imported, edge.getReceiverInterface().getVrfName()));
  }

  @Override
  @Nonnull
  public SymbolicRouteKey createCandidateKey(
      String receiver, AnnotatedRoute<IsisRoute> importedRoute) {
    return new SymbolicRouteKey(receiver, importedRoute.getSourceVrf(), importedRoute);
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<IsisRoute>> processExport(
      SymbolicRouteSession session, AnnotatedRoute<IsisRoute> selectedRoute) {
    BatfishIsisEdge edge = edge(session.getSessionId());
    if (!session.getSender().equals(edge.getSenderConfiguration().getHostname())
        || !session.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
      throw new IllegalArgumentException("IS-IS session endpoints do not match parsed edge");
    }
    return selectedRoute.getRoute().getLevel() == LEVEL_1
            && selectedRoute.getSourceVrf().equals(edge.getSenderInterface().getVrfName())
        ? Optional.of(selectedRoute)
        : Optional.empty();
  }

  @Override
  @Nonnull
  public String createExportMessageId(
      SymbolicRouteSession session,
      SymbolicRouteKey candidateKey,
      AnnotatedRoute<IsisRoute> exportedRoute) {
    Map<SymbolicRouteKey, String> identities = _exportIdentities.get(session.getSessionId());
    Map<SymbolicRouteKey, AnnotatedRoute<IsisRoute>> routes = _exports.get(session.getSessionId());
    if (identities == null || routes == null) {
      throw new IllegalArgumentException("unknown IS-IS edge session identity");
    }
    AnnotatedRoute<IsisRoute> previous = routes.putIfAbsent(candidateKey, exportedRoute);
    if (previous != null && !previous.equals(exportedRoute)) {
      throw new IllegalStateException(
          "IS-IS export changed within one fixed snapshot; use atomic route replacement");
    }
    return identities.computeIfAbsent(
        candidateKey, unused -> "isis-l1-candidate-" + identities.size());
  }

  private BatfishIsisEdge edge(String sessionId) {
    BatfishIsisEdge edge = _edges.get(sessionId);
    if (edge == null) {
      throw new IllegalArgumentException("unknown IS-IS edge session identity");
    }
    return edge;
  }

  private static void validateEndpoints(
      SymbolicRouteMessage<AnnotatedRoute<IsisRoute>> message, BatfishIsisEdge edge) {
    if (!message.getSender().equals(edge.getSenderConfiguration().getHostname())
        || !message.getReceiver().equals(edge.getReceiverConfiguration().getHostname())) {
      throw new IllegalArgumentException("IS-IS message endpoints do not match parsed edge");
    }
  }

  private static void requireActiveLevel1(org.batfish.datamodel.Interface iface) {
    if (iface.getIsis() == null
        || iface.getIsis().getLevel1() == null
        || iface.getIsis().getLevel1().getMode() != ACTIVE) {
      throw new IllegalArgumentException("IS-IS Level-1 point-to-point interface must be active");
    }
  }
}
