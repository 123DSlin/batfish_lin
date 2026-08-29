package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.IsisRoute.DEFAULT_METRIC;
import static org.batfish.datamodel.isis.IsisInterfaceMode.ACTIVE;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisLevel;
import org.batfish.dataplane.rib.IsisRib;

/** HoYAN Algorithm 2 adapter for one parser-derived IPv4 IS-IS level. */
public final class BatfishIsisProtocolAdapter
    implements SymbolicRouteProtocolAdapter<AnnotatedRoute<IsisRoute>> {

  @Nonnull private final Map<String, BatfishIsisEdge> _edges;
  @Nonnull private final Map<String, Map<SymbolicRouteKey, String>> _exportIdentities;
  @Nonnull private final Map<String, Map<SymbolicRouteKey, AnnotatedRoute<IsisRoute>>> _exports;
  @Nonnull private final IsisLevel _level;

  public BatfishIsisProtocolAdapter(Iterable<BatfishIsisEdge> edges) {
    this(edges, IsisLevel.LEVEL_1);
  }

  public BatfishIsisProtocolAdapter(Iterable<BatfishIsisEdge> edges, IsisLevel level) {
    _edges = new LinkedHashMap<>();
    _exportIdentities = new LinkedHashMap<>();
    _exports = new LinkedHashMap<>();
    _level = requireNonNull(level, "level must be provided");
    if (_level == IsisLevel.LEVEL_1_2) {
      throw new IllegalArgumentException("one guarded RIB adapter requires one IS-IS level");
    }
    for (BatfishIsisEdge edge : requireNonNull(edges, "edges must be provided")) {
      if (!edge.getEdge().getCircuitType().includes(_level)) {
        throw new IllegalArgumentException("IS-IS circuit does not carry adapter level");
      }
      if (_edges.put(edge.getSessionId(), edge) != null) {
        throw new IllegalArgumentException("duplicate IS-IS edge session identity");
      }
      requireActiveLevel(edge.getSenderInterface(), _level);
      requireActiveLevel(edge.getReceiverInterface(), _level);
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
      return message.getRoute().getRoute().getLevel() == _level
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
    if (neighborRoute.getLevel() != _level) {
      return Optional.empty();
    }
    IsisInterfaceLevelSettings settings = levelSettings(edge.getReceiverInterface(), _level);
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
    return selectedRoute.getRoute().getLevel() == _level
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
        candidateKey, unused -> "isis-" + levelName(_level) + "-candidate-" + identities.size());
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

  private static void requireActiveLevel(org.batfish.datamodel.Interface iface, IsisLevel level) {
    IsisInterfaceLevelSettings settings = levelSettings(iface, level);
    if (settings == null || settings.getMode() != ACTIVE) {
      throw new IllegalArgumentException("IS-IS point-to-point interface level must be active");
    }
  }

  private static IsisInterfaceLevelSettings levelSettings(
      org.batfish.datamodel.Interface iface, IsisLevel level) {
    if (iface.getIsis() == null) {
      return null;
    }
    return level == IsisLevel.LEVEL_1 ? iface.getIsis().getLevel1() : iface.getIsis().getLevel2();
  }

  private static String levelName(IsisLevel level) {
    return level == IsisLevel.LEVEL_1 ? "l1" : "l2";
  }
}
