package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.IsisRoute;

/** Final stable state produced by one complete symbolic route pipeline run. */
public final class BatfishSymbolicRoutePipelineResult {

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _mainRibNetwork;

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> _bgpRibNetwork;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _isisL1RibNetwork;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _isisL2RibNetwork;
  @Nonnull private final SymbolicRouteConvergenceResult _mainConvergence;
  @Nonnull private final SymbolicRouteConvergenceResult _bgpConvergence;
  @Nonnull private final SymbolicRouteConvergenceResult _isisL1Convergence;
  @Nonnull private final SymbolicRouteConvergenceResult _isisL2Convergence;
  @Nonnull private final ImmutableMap<String, ImmutableList<String>> _vrfsByRouter;

  BatfishSymbolicRoutePipelineResult(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainRibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpRibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisL1RibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisL2RibNetwork,
      SymbolicRouteConvergenceResult mainConvergence,
      SymbolicRouteConvergenceResult bgpConvergence,
      SymbolicRouteConvergenceResult isisL1Convergence,
      SymbolicRouteConvergenceResult isisL2Convergence,
      Map<String, Configuration> configurations) {
    _mainRibNetwork = requireNonNull(mainRibNetwork, "mainRibNetwork must be provided");
    _bgpRibNetwork = requireNonNull(bgpRibNetwork, "bgpRibNetwork must be provided");
    _isisL1RibNetwork = requireNonNull(isisL1RibNetwork, "isisL1RibNetwork must be provided");
    _isisL2RibNetwork = requireNonNull(isisL2RibNetwork, "isisL2RibNetwork must be provided");
    _mainConvergence = requireNonNull(mainConvergence, "mainConvergence must be provided");
    _bgpConvergence = requireNonNull(bgpConvergence, "bgpConvergence must be provided");
    _isisL1Convergence = requireNonNull(isisL1Convergence, "isisL1Convergence must be provided");
    _isisL2Convergence = requireNonNull(isisL2Convergence, "isisL2Convergence must be provided");
    ImmutableMap.Builder<String, ImmutableList<String>> vrfs = ImmutableMap.builder();
    requireNonNull(configurations, "configurations must be provided")
        .forEach(
            (router, configuration) ->
                vrfs.put(
                    router,
                    configuration.getVrfs().keySet().stream()
                        .sorted()
                        .collect(ImmutableList.toImmutableList())));
    _vrfsByRouter = vrfs.build();
  }

  @Nonnull
  public SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> getMainRibNetwork() {
    return _mainRibNetwork;
  }

  @Nonnull
  public SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> getBgpRibNetwork() {
    return _bgpRibNetwork;
  }

  @Nonnull
  public SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> getIsisL1RibNetwork() {
    return _isisL1RibNetwork;
  }

  @Nonnull
  public SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> getIsisL2RibNetwork() {
    return _isisL2RibNetwork;
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getMainConvergence() {
    return _mainConvergence;
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getBgpConvergence() {
    return _bgpConvergence;
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getIsisL1Convergence() {
    return _isisL1Convergence;
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getIsisL2Convergence() {
    return _isisL2Convergence;
  }

  /** Returns every main, BGP, and IS-IS L1 candidate in deterministic router/VRF order. */
  @Nonnull
  public ImmutableList<SymbolicRibRecord> getAllRoutes() {
    return getAllRoutes(true);
  }

  @Nonnull
  private ImmutableList<SymbolicRibRecord> getAllRoutes(boolean simplifyGuards) {
    List<SymbolicRibRecord> records = new ArrayList<>();
    _mainRibNetwork
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            records.add(
                                SymbolicRibRecord.from(
                                    SymbolicRibRecord.Plane.MAIN, rib, entry, simplifyGuards))));
    _bgpRibNetwork
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            records.add(
                                SymbolicRibRecord.from(
                                    SymbolicRibRecord.Plane.BGP, rib, entry, simplifyGuards))));
    _isisL1RibNetwork
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            records.add(
                                SymbolicRibRecord.from(
                                    SymbolicRibRecord.Plane.ISIS_L1, rib, entry, simplifyGuards))));
    _isisL2RibNetwork
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            records.add(
                                SymbolicRibRecord.from(
                                    SymbolicRibRecord.Plane.ISIS_L2, rib, entry, simplifyGuards))));
    records.sort(SymbolicRibRecord.ordering());
    return ImmutableList.copyOf(records);
  }

  /** Returns the final records grouped exactly as router -&gt; VRF -&gt; guarded RIB entries. */
  @Nonnull
  public ImmutableMap<String, Map<String, ImmutableList<SymbolicRibRecord>>>
      getRoutesByRouterAndVrf() {
    Map<String, Map<String, List<SymbolicRibRecord>>> grouped = new LinkedHashMap<>();
    _vrfsByRouter.forEach(
        (router, vrfs) -> {
          Map<String, List<SymbolicRibRecord>> byVrf = new LinkedHashMap<>();
          vrfs.forEach(vrf -> byVrf.put(vrf, new ArrayList<>()));
          grouped.put(router, byVrf);
        });
    for (SymbolicRibRecord record : getAllRoutes()) {
      grouped
          .computeIfAbsent(record.getRouter(), unused -> new LinkedHashMap<>())
          .computeIfAbsent(record.getVrf(), unused -> new ArrayList<>())
          .add(record);
    }
    ImmutableMap.Builder<String, Map<String, ImmutableList<SymbolicRibRecord>>> routers =
        ImmutableMap.builder();
    grouped.forEach(
        (router, byVrf) -> {
          ImmutableMap.Builder<String, ImmutableList<SymbolicRibRecord>> vrfs =
              ImmutableMap.builder();
          byVrf.forEach((vrf, records) -> vrfs.put(vrf, ImmutableList.copyOf(records)));
          routers.put(router, vrfs.build());
        });
    return routers.build();
  }

  /** Returns one configured router/VRF's complete guarded RIB, including an empty RIB. */
  @Nonnull
  public ImmutableList<SymbolicRibRecord> getRoutes(String router, String vrf) {
    requireNonNull(router, "router must be provided");
    requireNonNull(vrf, "vrf must be provided");
    Map<String, ImmutableList<SymbolicRibRecord>> byVrf = getRoutesByRouterAndVrf().get(router);
    if (byVrf == null) {
      throw new IllegalArgumentException("router is not present in the pipeline input");
    }
    ImmutableList<SymbolicRibRecord> routes = byVrf.get(vrf);
    if (routes == null) {
      throw new IllegalArgumentException("VRF is not present in the router configuration");
    }
    return routes;
  }

  /** Produces the user-facing whole-network guarded RIB report as deterministic pretty JSON. */
  @Nonnull
  public String toJson() {
    try {
      return BatfishObjectMapper.writePrettyString(getRoutesByRouterAndVrf());
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize symbolic RIB report", e);
    }
  }

  /** Produces a router/VRF report intended for direct human review. */
  @Nonnull
  public String toReadableText() {
    return toReadableText(true);
  }

  /** Produces the same report with the exact guard expressions held by the stable RIBs. */
  @Nonnull
  public String toRawReadableText() {
    return toReadableText(false);
  }

  private String toReadableText(boolean simplifyGuards) {
    StringBuilder output = new StringBuilder("SYMBOLIC ROUTING INFORMATION BASE\n");
    output.append("Guards describe route availability and final selection conditions.\n");
    output.append("\nMAIN RIB (cross-protocol forwarding candidates)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.MAIN, simplifyGuards);
    output.append("\nBGP LOC-RIB (protocol detail)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.BGP, simplifyGuards);
    output.append("\nIS-IS LEVEL-1 RIB (protocol detail)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.ISIS_L1, simplifyGuards);
    output.append("\nIS-IS LEVEL-2 RIB (protocol detail)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.ISIS_L2, simplifyGuards);
    return output.toString();
  }

  private void appendReadableTable(
      StringBuilder output, SymbolicRibRecord.Plane plane, boolean simplifyGuards) {
    output.append(
        String.format(
            "%-8s %-9s %-18s %-10s %-16s %-18s %-28s %-55s %s%n",
            "Node",
            "VRF",
            "Network",
            "Protocol",
            "NextHopIP",
            "NextHopInterface",
            "AvailabilityGuard",
            "SelectionGuard",
            "Path"));
    output.append(
        "========================================================================================================================================================================\n");
    for (SymbolicRibRecord route : getAllRoutes(simplifyGuards)) {
      if (route.getPlane() != plane) {
        continue;
      }
      output.append(
          String.format(
              "%-8s %-9s %-18s %-10s %-16s %-18s %-28s %-55s %s%n",
              route.getRouter(),
              route.getVrf(),
              route.getPrefix(),
              route.getProtocol(),
              route.getNextHopIp(),
              route.getNextHopInterface(),
              oneLine(route.getAvailabilityGuard()),
              oneLine(route.getSelectionGuard()),
              String.join(" -> ", route.getRouterPath())));
    }
  }

  private static String oneLine(String value) {
    return value.replaceAll("\\s+", " ").trim();
  }
}
