package org.batfish.minesweeper.smt;

import static com.google.common.base.MoreObjects.firstNonNull;
import static org.batfish.datamodel.isis.IsisInterfaceMode.ACTIVE;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.BoolExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Expr;
import com.microsoft.z3.Solver;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nullable;
import org.batfish.common.BatfishException;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisLevel;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.minesweeper.GraphEdge;
import org.batfish.minesweeper.Protocol;

/** Link-state IS-IS encoding used directly by a Minesweeper {@link EncoderSlice}. */
public final class IsisSpfSmtEncoder {

  public static final long MAX_WIDE_METRIC = 0xFFFFFFL;

  /** Per-slice SPF result consumed by MAIN-RIB and forwarding constraints. */
  static final class SliceEncoding {
    private final Map<String, Map<Protocol, Map<GraphEdge, BoolExpr>>> _nextHops;
    private final Map<Protocol, Map<Prefix, Map<String, PrefixState>>> _states;

    private SliceEncoding(
        Map<String, Map<Protocol, Map<GraphEdge, BoolExpr>>> nextHops,
        Map<Protocol, Map<Prefix, Map<String, PrefixState>>> states) {
      _nextHops = nextHops;
      _states = states;
    }

    Map<GraphEdge, BoolExpr> nextHops(String router, Protocol protocol) {
      return _nextHops
          .getOrDefault(router, Collections.emptyMap())
          .getOrDefault(protocol, Collections.emptyMap());
    }

    BoolExpr routeAvailable(EncoderSlice slice, String router, Prefix prefix) {
      List<BoolExpr> available = new ArrayList<>();
      for (Protocol protocol : List.of(Protocol.ISIS_L1, Protocol.ISIS_L2)) {
        PrefixState state =
            _states
                .getOrDefault(protocol, Collections.emptyMap())
                .getOrDefault(prefix, Collections.emptyMap())
                .get(router);
        if (state != null) {
          available.add(state._reachable);
        }
      }
      return or(slice, available);
    }

    Map<GraphEdge, BoolExpr> nextHopsToPrefix(EncoderSlice slice, String router, Prefix prefix) {
      Map<GraphEdge, BoolExpr> result = new LinkedHashMap<>();
      for (Protocol protocol : List.of(Protocol.ISIS_L1, Protocol.ISIS_L2)) {
        PrefixState state =
            _states
                .getOrDefault(protocol, Collections.emptyMap())
                .getOrDefault(prefix, Collections.emptyMap())
                .get(router);
        if (state != null) {
          state._nextHops.forEach((edge, guard) -> result.merge(edge, guard, slice::mkOr));
        }
      }
      return result;
    }
  }

  private static final class PrefixState {
    private final BoolExpr _reachable;
    private final ArithExpr _distance;
    private final Map<GraphEdge, BoolExpr> _nextHops;

    private PrefixState(BoolExpr reachable, ArithExpr distance, Map<GraphEdge, BoolExpr> nextHops) {
      _reachable = reachable;
      _distance = distance;
      _nextHops = nextHops;
    }
  }

  private IsisSpfSmtEncoder() {}

  /** Declares and pins parsed IS-IS interface metrics as ordinary SpecLens Config fields. */
  static void initConfigurationConstants(
      Context ctx,
      Solver solver,
      Map<String, Expr> allVariables,
      Map<String, Configuration> configurations) {
    configurations.forEach(
        (hostname, configuration) ->
            configuration
                .getAllInterfaces(Configuration.DEFAULT_VRF_NAME)
                .values()
                .forEach(
                    iface -> {
                      if (iface.getIsis() == null) {
                        return;
                      }
                      initLevelCost(
                          ctx,
                          solver,
                          allVariables,
                          hostname,
                          iface,
                          IsisLevel.LEVEL_1,
                          iface.getIsis().getLevel1());
                      initLevelCost(
                          ctx,
                          solver,
                          allVariables,
                          hostname,
                          iface,
                          IsisLevel.LEVEL_2,
                          iface.getIsis().getLevel2());
                    }));
  }

  /**
   * Builds destination-parametric L1/L2 SPF equations. No route advertisement variable is used:
   * every router chooses all equal-cost next hops from its level-specific link-state graph.
   */
  static SliceEncoding encode(EncoderSlice slice) {
    Map<String, Configuration> configurations = slice.getGraph().getConfigurations();
    configurations.values().forEach(IsisSpfSmtEncoder::validateProcess);

    Map<Protocol, Map<Prefix, Map<String, BoolExpr>>> nativeOrigins = new LinkedHashMap<>();
    nativeOrigins.put(Protocol.ISIS_L1, collectNativeOrigins(slice, Protocol.ISIS_L1));
    nativeOrigins.put(Protocol.ISIS_L2, collectNativeOrigins(slice, Protocol.ISIS_L2));

    // An L1/L2 router originates the attached default into L1.
    for (Map.Entry<String, Configuration> entry : configurations.entrySet()) {
      IsisProcess process = entry.getValue().getDefaultVrf().getIsisProcess();
      if (process != null
          && process.getLevel1() != null
          && process.getLevel2() != null
          && !process.getOverload()) {
        nativeOrigins
            .get(Protocol.ISIS_L1)
            .computeIfAbsent(Prefix.ZERO, unused -> new LinkedHashMap<>())
            .put(entry.getKey(), slice.mkTrue());
      }
    }

    Map<Protocol, Map<Prefix, Map<String, PrefixState>>> states = new LinkedHashMap<>();
    Map<Prefix, Map<String, PrefixState>> l1 = new LinkedHashMap<>();
    for (Prefix prefix : sortedPrefixes(nativeOrigins.get(Protocol.ISIS_L1).keySet())) {
      l1.put(
          prefix,
          encodePrefix(
              slice,
              Protocol.ISIS_L1,
              prefix,
              nativeOrigins.get(Protocol.ISIS_L1).get(prefix),
              Collections.emptyMap()));
    }
    states.put(Protocol.ISIS_L1, l1);

    // L1 routes are leaked into L2 at non-overloaded L1/L2 routers, preserving their L1 metric.
    Set<Prefix> l2Prefixes = new LinkedHashSet<>(nativeOrigins.get(Protocol.ISIS_L2).keySet());
    l2Prefixes.addAll(nativeOrigins.get(Protocol.ISIS_L1).keySet());
    l2Prefixes.remove(Prefix.ZERO);
    Map<Prefix, Map<String, PrefixState>> l2 = new LinkedHashMap<>();
    for (Prefix prefix : sortedPrefixes(l2Prefixes)) {
      Map<String, PrefixState> transitions = new LinkedHashMap<>();
      for (Map.Entry<String, Configuration> entry : configurations.entrySet()) {
        IsisProcess process = entry.getValue().getDefaultVrf().getIsisProcess();
        PrefixState l1State = l1.getOrDefault(prefix, Collections.emptyMap()).get(entry.getKey());
        if (l1State != null
            && process != null
            && process.getLevel1() != null
            && process.getLevel2() != null
            && !process.getOverload()) {
          transitions.put(entry.getKey(), l1State);
        }
      }
      l2.put(
          prefix,
          encodePrefix(
              slice,
              Protocol.ISIS_L2,
              prefix,
              nativeOrigins.get(Protocol.ISIS_L2).getOrDefault(prefix, Collections.emptyMap()),
              transitions));
    }
    states.put(Protocol.ISIS_L2, l2);

    Map<String, Map<Protocol, Map<GraphEdge, BoolExpr>>> bestNextHops = new LinkedHashMap<>();
    for (String router : sorted(configurations.keySet())) {
      for (Protocol protocol : List.of(Protocol.ISIS_L1, Protocol.ISIS_L2)) {
        if (!slice.getProtocols().get(router).contains(protocol)) {
          continue;
        }
        SymbolicRouteBV best =
            slice.getSymbolicDecisions().getBestVars(slice.getOptimizations(), router, protocol);
        Map<GraphEdge, BoolExpr> forwarding =
            constrainProtocolBest(slice, router, protocol, best, states.get(protocol));
        bestNextHops
            .computeIfAbsent(router, unused -> new LinkedHashMap<>())
            .put(protocol, forwarding);
      }
      constrainLevelPreference(slice, router);
    }
    return new SliceEncoding(bestNextHops, states);
  }

  /**
   * Batfish's combined {@code IsisRib} prefers L1 over L2 before comparing the metric. The generic
   * MAIN-RIB comparison has no IS-IS level field, so explicitly rule out selecting L2 when both
   * levels provide an equally specific route. A more-specific L2 route is still selected normally.
   */
  private static void constrainLevelPreference(EncoderSlice slice, String router) {
    if (!slice
        .getProtocols()
        .get(router)
        .containsAll(List.of(Protocol.ISIS_L1, Protocol.ISIS_L2))) {
      return;
    }
    SymbolicRouteBV l1 =
        slice
            .getSymbolicDecisions()
            .getBestVars(slice.getOptimizations(), router, Protocol.ISIS_L1);
    SymbolicRouteBV l2 =
        slice
            .getSymbolicDecisions()
            .getBestVars(slice.getOptimizations(), router, Protocol.ISIS_L2);
    SymbolicRouteBV overall = slice.getSymbolicDecisions().getBestNeighbor().get(router);
    if (l1 == null || l2 == null || overall == null || overall.getProtocolHistory() == null) {
      return;
    }
    BoolExpr samePrefixLength = slice.mkEq(l1.getPrefixLength(), l2.getPrefixLength());
    BoolExpr bothLevels = slice.mkAnd(l1.getPermitted(), l2.getPermitted(), samePrefixLength);
    slice.add(
        slice.mkImplies(
            bothLevels, slice.mkNot(overall.getProtocolHistory().checkIfValue(Protocol.ISIS_L2))));
  }

  private static Map<Prefix, Map<String, BoolExpr>> collectNativeOrigins(
      EncoderSlice slice, Protocol protocol) {
    Map<Prefix, Map<String, BoolExpr>> origins = new LinkedHashMap<>();
    for (String router : sorted(slice.getGraph().getConfigurations().keySet())) {
      Configuration configuration = slice.getGraph().getConfigurations().get(router);
      if (!slice.getProtocols().get(router).contains(protocol)) {
        continue;
      }
      List<Interface> interfaces =
          new ArrayList<>(configuration.getAllInterfaces(Configuration.DEFAULT_VRF_NAME).values());
      interfaces.sort(Comparator.comparing(Interface::getName));
      for (Interface iface : interfaces) {
        IsisInterfaceLevelSettings settings = settings(iface, protocol);
        if (!iface.getActive() || iface.getConcreteAddress() == null || settings == null) {
          continue;
        }
        BoolExpr guard =
            settings.getMode() == ACTIVE
                ? interfaceUp(slice, router, iface.getName())
                : slice.mkTrue();
        origins
            .computeIfAbsent(
                iface.getConcreteAddress().getPrefix(), unused -> new LinkedHashMap<>())
            .merge(router, guard, slice::mkOr);
      }
    }
    return origins;
  }

  private static Map<String, PrefixState> encodePrefix(
      EncoderSlice slice,
      Protocol protocol,
      Prefix prefix,
      Map<String, BoolExpr> nativeOrigins,
      Map<String, PrefixState> transitions) {
    Map<String, PrefixState> result = new LinkedHashMap<>();
    Map<String, ArithExpr> distances = new LinkedHashMap<>();
    Map<String, ArithExpr> ranks = new LinkedHashMap<>();
    Map<String, BoolExpr> reachable = new LinkedHashMap<>();
    List<String> routers = levelRouters(slice, protocol);
    // An L2 route can contain an L1 path followed by an L2 path through a transition router.
    long maxDistance = Math.max(1L, 2L * routers.size()) * MAX_WIDE_METRIC;
    for (String router : routers) {
      String stem = stem(slice, protocol, prefix, router);
      ArithExpr distance = slice.getCtx().mkIntConst(stem + "_distance");
      ArithExpr rank = slice.getCtx().mkIntConst(stem + "_rank");
      BoolExpr reach = slice.getCtx().mkBoolConst(stem + "_reachable");
      register(slice, distance, rank, reach);
      slice.add(
          slice.mkAnd(
              slice.mkGe(distance, slice.mkInt(0)),
              slice.mkLe(distance, slice.mkInt(maxDistance))));
      slice.add(
          slice.mkAnd(
              slice.mkGe(rank, slice.mkInt(0)), slice.mkLe(rank, slice.mkInt(routers.size()))));
      distances.put(router, distance);
      ranks.put(router, rank);
      reachable.put(router, reach);
    }

    for (String router : routers) {
      String stem = stem(slice, protocol, prefix, router);
      BoolExpr nativeOrigin = nativeOrigins.getOrDefault(router, slice.mkFalse());
      PrefixState transition = transitions.get(router);
      BoolExpr transitionOrigin = transition == null ? slice.mkFalse() : transition._reachable;
      ArithExpr distance = distances.get(router);
      ArithExpr rank = ranks.get(router);
      List<BoolExpr> choices = new ArrayList<>();
      BoolExpr nativeChoice = slice.mkAnd(nativeOrigin, slice.mkEq(distance, slice.mkInt(0)));
      choices.add(nativeChoice);
      slice.add(slice.mkImplies(nativeOrigin, slice.mkLe(distance, slice.mkInt(0))));
      if (transition != null) {
        BoolExpr transitionChoice =
            slice.mkAnd(transitionOrigin, slice.mkEq(distance, transition._distance));
        choices.add(transitionChoice);
        slice.add(slice.mkImplies(transitionOrigin, slice.mkLe(distance, transition._distance)));
      }
      BoolExpr sourceChoice = or(slice, choices);
      slice.add(slice.mkImplies(sourceChoice, slice.mkEq(rank, slice.mkInt(0))));

      Map<GraphEdge, BoolExpr> nextHops = new LinkedHashMap<>();
      for (GraphEdge edge : sortedEdges(slice.getGraph().getEdgeMap().get(router))) {
        if (!isAdjacency(slice, edge, protocol) || !reachable.containsKey(edge.getPeer())) {
          continue;
        }
        String name = stem + "_ecmp_" + sanitize(edge.getStart().getName());
        BoolExpr nextHop = slice.getCtx().mkBoolConst(name);
        register(slice, nextHop);
        ArithExpr via =
            slice.mkSum(
                cost(slice, router, edge.getStart(), protocol), distances.get(edge.getPeer()));
        BoolExpr viable =
            slice.mkAnd(
                edgeUp(slice, edge),
                reachable.get(edge.getPeer()),
                mayTransit(slice, edge.getPeer(), nativeOrigins, transitions));
        BoolExpr exact = slice.mkAnd(viable, slice.mkEq(distance, via));
        slice.add(slice.mkEq(nextHop, exact));
        slice.add(slice.mkImplies(viable, slice.mkLe(distance, via)));
        slice.add(slice.mkImplies(nextHop, slice.mkGt(rank, ranks.get(edge.getPeer()))));
        choices.add(nextHop);
        nextHops.put(edge, nextHop);
      }
      BoolExpr anyChoice = or(slice, choices);
      slice.add(slice.mkEq(reachable.get(router), anyChoice));
      result.put(router, new PrefixState(reachable.get(router), distance, nextHops));
    }
    return result;
  }

  private static Map<GraphEdge, BoolExpr> constrainProtocolBest(
      EncoderSlice slice,
      String router,
      Protocol protocol,
      SymbolicRouteBV best,
      Map<Prefix, Map<String, PrefixState>> states) {
    List<BoolExpr> available = new ArrayList<>();
    List<BoolExpr> selected = new ArrayList<>();
    Map<GraphEdge, List<BoolExpr>> nextHopTerms = new LinkedHashMap<>();
    for (Prefix prefix : sortedPrefixes(states.keySet())) {
      PrefixState state = states.get(prefix).get(router);
      if (state == null) {
        continue;
      }
      BoolExpr routeAvailable =
          slice.mkAnd(
              state._reachable, slice.isRelevantFor(prefix, slice.getSymbolicPacket().getDstIp()));
      BoolExpr routeSelected =
          slice.mkAnd(
              routeAvailable,
              slice.mkEq(best.getPrefixLength(), slice.mkInt(prefix.getPrefixLength())),
              slice.mkEq(best.getMetric(), state._distance));
      available.add(routeAvailable);
      selected.add(routeSelected);
      slice.add(
          slice.mkImplies(
              routeAvailable,
              slice.mkGe(best.getPrefixLength(), slice.mkInt(prefix.getPrefixLength()))));
      slice.add(
          slice.mkImplies(
              slice.mkAnd(
                  routeAvailable,
                  slice.mkEq(best.getPrefixLength(), slice.mkInt(prefix.getPrefixLength()))),
              slice.mkLe(best.getMetric(), state._distance)));
      for (Map.Entry<GraphEdge, BoolExpr> nextHop : state._nextHops.entrySet()) {
        nextHopTerms
            .computeIfAbsent(nextHop.getKey(), unused -> new ArrayList<>())
            .add(slice.mkAnd(routeSelected, nextHop.getValue()));
      }
    }
    BoolExpr permitted = or(slice, available);
    slice.add(slice.mkEq(best.getPermitted(), permitted));
    slice.add(slice.mkImplies(permitted, or(slice, selected)));
    Configuration configuration = slice.getGraph().getConfigurations().get(router);
    int admin =
        (protocol.isIsisL1() ? RoutingProtocol.ISIS_L1 : RoutingProtocol.ISIS_L2)
            .getDefaultAdministrativeCost(configuration.getConfigurationFormat());
    slice.add(slice.mkImplies(permitted, slice.safeEq(best.getAdminDist(), slice.mkInt(admin))));
    Map<GraphEdge, BoolExpr> forwarding = new LinkedHashMap<>();
    nextHopTerms.forEach((edge, terms) -> forwarding.put(edge, or(slice, terms)));
    return forwarding;
  }

  private static ArithExpr cost(
      EncoderSlice slice, String router, Interface iface, Protocol protocol) {
    String name =
        costVariable(
            router, iface.getName(), protocol.isIsisL1() ? IsisLevel.LEVEL_1 : IsisLevel.LEVEL_2);
    Expr value = slice.getAllVariables().get(name);
    if (!(value instanceof ArithExpr)) {
      throw new BatfishException("missing IS-IS cost variable " + name);
    }
    return (ArithExpr) value;
  }

  private static boolean isAdjacency(EncoderSlice slice, GraphEdge edge, Protocol protocol) {
    if (edge.getPeer() == null || edge.isAbstract()) {
      return false;
    }
    Configuration peer = slice.getGraph().getConfigurations().get(edge.getPeer());
    GraphEdge other = slice.getGraph().getOtherEnd().get(edge);
    Configuration local = slice.getGraph().getConfigurations().get(edge.getRouter());
    if (local == null
        || peer == null
        || other == null
        || activeSettings(edge.getStart(), protocol) == null
        || activeSettings(other.getStart(), protocol) == null) {
      return false;
    }
    IsisProcess localProcess = local.getDefaultVrf().getIsisProcess();
    IsisProcess peerProcess = peer.getDefaultVrf().getIsisProcess();
    if (localProcess == null
        || peerProcess == null
        || Arrays.equals(
            localProcess.getNetAddress().getSystemId(),
            peerProcess.getNetAddress().getSystemId())) {
      return false;
    }
    return !protocol.isIsisL1()
        || Arrays.equals(
            localProcess.getNetAddress().getAreaId(), peerProcess.getNetAddress().getAreaId());
  }

  /** An overloaded router may remain a destination, but must not be used as SPF transit. */
  private static BoolExpr mayTransit(
      EncoderSlice slice,
      String router,
      Map<String, BoolExpr> nativeOrigins,
      Map<String, PrefixState> transitions) {
    Configuration configuration = slice.getGraph().getConfigurations().get(router);
    IsisProcess process =
        configuration == null ? null : configuration.getDefaultVrf().getIsisProcess();
    if (process == null || !process.getOverload()) {
      return slice.mkTrue();
    }
    List<BoolExpr> destination = new ArrayList<>();
    destination.add(nativeOrigins.getOrDefault(router, slice.mkFalse()));
    PrefixState transition = transitions.get(router);
    if (transition != null) {
      destination.add(transition._reachable);
    }
    return or(slice, destination);
  }

  @Nullable
  private static IsisInterfaceLevelSettings activeSettings(Interface iface, Protocol protocol) {
    IsisInterfaceLevelSettings settings = settings(iface, protocol);
    return settings != null && settings.getMode() == ACTIVE ? settings : null;
  }

  @Nullable
  private static IsisInterfaceLevelSettings settings(Interface iface, Protocol protocol) {
    if (iface.getIsis() == null) {
      return null;
    }
    return protocol.isIsisL1() ? iface.getIsis().getLevel1() : iface.getIsis().getLevel2();
  }

  private static BoolExpr interfaceUp(EncoderSlice slice, String router, String iface) {
    for (GraphEdge edge : slice.getGraph().getEdgeMap().get(router)) {
      if (edge.getStart().getName().equals(iface)) {
        return edgeUp(slice, edge);
      }
    }
    return slice.mkFalse();
  }

  static BoolExpr edgeUp(EncoderSlice slice, GraphEdge edge) {
    ArithExpr failed = slice.getSymbolicFailures().getFailedVariable(edge);
    ArithExpr failedStart = slice.getSymbolicFailures().getFailedStartVariable(edge);
    BoolExpr up =
        slice.mkAnd(slice.mkEq(failed, slice.mkInt(0)), slice.mkEq(failedStart, slice.mkInt(0)));
    if (slice.getSymbolicFailures().getFailedPeerVariable(edge).isPresent()) {
      up =
          slice.mkAnd(
              up,
              slice.mkEq(
                  slice.getSymbolicFailures().getFailedPeerVariable(edge).get(), slice.mkInt(0)));
    }
    return up;
  }

  private static List<String> levelRouters(EncoderSlice slice, Protocol protocol) {
    List<String> routers = new ArrayList<>();
    for (String router : slice.getGraph().getConfigurations().keySet()) {
      if (slice.getProtocols().get(router).contains(protocol)) {
        routers.add(router);
      }
    }
    Collections.sort(routers);
    return routers;
  }

  private static void initLevelCost(
      Context ctx,
      Solver solver,
      Map<String, Expr> allVariables,
      String hostname,
      Interface iface,
      IsisLevel level,
      @Nullable IsisInterfaceLevelSettings settings) {
    if (settings == null || settings.getMode() != ACTIVE) {
      return;
    }
    String name = costVariable(hostname, iface.getName(), level);
    ArithExpr variable = ctx.mkIntConst(name);
    long pin = firstNonNull(settings.getCost(), IsisRoute.DEFAULT_METRIC);
    allVariables.put(variable.toString(), variable);
    solver.add(ctx.mkEq(variable, ctx.mkInt(pin)));
    solver.add(ctx.mkGe(variable, ctx.mkInt(0)));
    solver.add(ctx.mkLe(variable, ctx.mkInt(MAX_WIDE_METRIC)));
  }

  public static String costVariable(String hostname, String interfaceName, IsisLevel level) {
    if (level != IsisLevel.LEVEL_1 && level != IsisLevel.LEVEL_2) {
      throw new IllegalArgumentException("IS-IS cost variable requires L1 or L2");
    }
    return "Config_"
        + sanitize(hostname)
        + "_Interface_"
        + sanitize(interfaceName)
        + "_Isis_"
        + (level == IsisLevel.LEVEL_1 ? "L1" : "L2")
        + "_cost";
  }

  private static void validateProcess(Configuration configuration) {
    IsisProcess process = configuration.getDefaultVrf().getIsisProcess();
    if (process != null
        && (process.getExportPolicy() != null || !process.getGeneratedRoutes().isEmpty())) {
      throw new BatfishException(
          "IS-IS SMT redistribution/generated routes are not implemented on "
              + configuration.getHostname());
    }
  }

  private static BoolExpr or(EncoderSlice slice, List<BoolExpr> expressions) {
    return expressions.isEmpty()
        ? slice.mkFalse()
        : slice.mkOr(expressions.toArray(new BoolExpr[0]));
  }

  private static void register(EncoderSlice slice, Expr... expressions) {
    for (Expr expression : expressions) {
      slice.getAllVariables().put(expression.toString(), expression);
    }
  }

  private static List<Prefix> sortedPrefixes(Set<Prefix> prefixes) {
    List<Prefix> sorted = new ArrayList<>(prefixes);
    sorted.sort(Comparator.naturalOrder());
    return sorted;
  }

  private static List<GraphEdge> sortedEdges(List<GraphEdge> edges) {
    List<GraphEdge> sorted = new ArrayList<>(edges);
    sorted.sort(
        Comparator.comparing((GraphEdge edge) -> edge.getStart().getName())
            .thenComparing(edge -> edge.getPeer() == null ? "" : edge.getPeer()));
    return sorted;
  }

  private static List<String> sorted(Set<String> values) {
    List<String> sorted = new ArrayList<>(values);
    Collections.sort(sorted);
    return sorted;
  }

  private static String stem(EncoderSlice slice, Protocol protocol, Prefix prefix, String router) {
    return slice.getEncoder().getId()
        + "_"
        + sanitize(slice.getSliceName())
        + "ISIS-SPF_"
        + protocol.name()
        + "_"
        + sanitize(router)
        + "_"
        + sanitize(prefix.toString());
  }

  private static String sanitize(String raw) {
    return raw.replaceAll("[^A-Za-z0-9_]", "_");
  }
}
