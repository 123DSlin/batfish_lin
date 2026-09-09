package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import javax.annotation.Nonnull;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicsr.GuardedSidDatabase;
import org.batfish.minesweeper.symbolicsr.GuardedSidReconciler;
import org.batfish.minesweeper.symbolicsr.GuardedSrPolicyDatabase;
import org.batfish.minesweeper.symbolicsr.GuardedSrPolicyReconciler;
import org.batfish.minesweeper.symbolicsr.SymbolicSrPolicyExport;
import org.batfish.minesweeper.symbolicsr.SymbolicSrPolicyRecord;

/** Final stable state produced by one complete symbolic route pipeline run. */
public final class BatfishSymbolicRoutePipelineResult {

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _mainRibNetwork;

  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> _bgpRibNetwork;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _isisL1RibNetwork;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> _isisL2RibNetwork;
  @Nonnull private final BatfishIsisLevelTransitionReconciler _isisLevelTransitionReconciler;
  @Nonnull private final BatfishMainRibReconciler _mainRibReconciler;
  @Nonnull private final BatfishBgpRedistributionReconciler _bgpRedistributionReconciler;
  @Nonnull private final BatfishStaticRouteReconciler _staticRouteReconciler;
  @Nonnull private final SymbolicRouteConvergenceResult _mainConvergence;
  @Nonnull private final SymbolicRouteConvergenceResult _bgpConvergence;
  @Nonnull private final SymbolicRouteConvergenceResult _isisL1Convergence;
  @Nonnull private final SymbolicRouteConvergenceResult _isisL2Convergence;
  @Nonnull private final GuardedSidReconciler _guardedSidReconciler;
  @Nonnull private final GuardedSrPolicyReconciler _guardedSrPolicyReconciler;
  @Nonnull private final ImmutableMap<String, ImmutableList<String>> _vrfsByRouter;

  @Nonnull private final ImmutableMap<String, LinkFailureKey> _linkFailureKeysByGuardVariable;

  BatfishSymbolicRoutePipelineResult(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainRibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpRibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisL1RibNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<IsisRoute>> isisL2RibNetwork,
      BatfishIsisLevelTransitionReconciler isisLevelTransitionReconciler,
      BatfishMainRibReconciler mainRibReconciler,
      BatfishBgpRedistributionReconciler bgpRedistributionReconciler,
      BatfishStaticRouteReconciler staticRouteReconciler,
      SymbolicRouteConvergenceResult mainConvergence,
      SymbolicRouteConvergenceResult bgpConvergence,
      SymbolicRouteConvergenceResult isisL1Convergence,
      SymbolicRouteConvergenceResult isisL2Convergence,
      GuardedSidReconciler guardedSidReconciler,
      GuardedSrPolicyReconciler guardedSrPolicyReconciler,
      Map<String, Configuration> configurations,
      Map<String, LinkFailureKey> linkFailureKeysByGuardVariable) {
    _mainRibNetwork = requireNonNull(mainRibNetwork, "mainRibNetwork must be provided");
    _bgpRibNetwork = requireNonNull(bgpRibNetwork, "bgpRibNetwork must be provided");
    _isisL1RibNetwork = requireNonNull(isisL1RibNetwork, "isisL1RibNetwork must be provided");
    _isisL2RibNetwork = requireNonNull(isisL2RibNetwork, "isisL2RibNetwork must be provided");
    _isisLevelTransitionReconciler =
        requireNonNull(
            isisLevelTransitionReconciler, "isisLevelTransitionReconciler must be provided");
    _mainRibReconciler = requireNonNull(mainRibReconciler, "mainRibReconciler must be provided");
    _bgpRedistributionReconciler =
        requireNonNull(bgpRedistributionReconciler, "bgpRedistributionReconciler must be provided");
    _staticRouteReconciler =
        requireNonNull(staticRouteReconciler, "staticRouteReconciler must be provided");
    _mainConvergence = requireNonNull(mainConvergence, "mainConvergence must be provided");
    _bgpConvergence = requireNonNull(bgpConvergence, "bgpConvergence must be provided");
    _isisL1Convergence = requireNonNull(isisL1Convergence, "isisL1Convergence must be provided");
    _isisL2Convergence = requireNonNull(isisL2Convergence, "isisL2Convergence must be provided");
    _guardedSidReconciler =
        requireNonNull(guardedSidReconciler, "guardedSidReconciler must be provided");
    _guardedSrPolicyReconciler =
        requireNonNull(guardedSrPolicyReconciler, "guardedSrPolicyReconciler must be provided");
    _linkFailureKeysByGuardVariable =
        ImmutableMap.copyOf(
            requireNonNull(
                linkFailureKeysByGuardVariable,
                "linkFailureKeysByGuardVariable must be provided"));
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
  public BatfishIsisLevelTransitionReconciler getIsisLevelTransitionReconciler() {
    return _isisLevelTransitionReconciler;
  }

  @Nonnull
  public BatfishMainRibReconciler getMainRibReconciler() {
    return _mainRibReconciler;
  }

  @Nonnull
  public BatfishBgpRedistributionReconciler getBgpRedistributionReconciler() {
    return _bgpRedistributionReconciler;
  }

  @Nonnull
  public BatfishStaticRouteReconciler getStaticRouteReconciler() {
    return _staticRouteReconciler;
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

  @Nonnull
  public GuardedSidDatabase getGuardedSidDatabase() {
    return _guardedSidReconciler.getDatabase();
  }

  @Nonnull
  public GuardedSidReconciler getGuardedSidReconciler() {
    return _guardedSidReconciler;
  }

  @Nonnull
  public GuardedSrPolicyDatabase getGuardedSrPolicyDatabase() {
    return _guardedSrPolicyReconciler.getDatabase();
  }

  @Nonnull
  public GuardedSrPolicyReconciler getGuardedSrPolicyReconciler() {
    return _guardedSrPolicyReconciler;
  }

  /** Canonical link identity for each link-up guard variable discovered from parsed topology. */
  @Nonnull
  public ImmutableMap<String, LinkFailureKey> getLinkFailureKeysByGuardVariable() {
    return _linkFailureKeysByGuardVariable;
  }

  /** Returns candidates followed by forwarding branches in deterministic semantic-key order. */
  @Nonnull
  public ImmutableList<SymbolicSrPolicyRecord> getAllSrPolicyRecords() {
    return getAllSrPolicyRecords(true);
  }

  @Nonnull
  private ImmutableList<SymbolicSrPolicyRecord> getAllSrPolicyRecords(boolean simplifyGuards) {
    List<SymbolicSrPolicyRecord> records = new ArrayList<>();
    getGuardedSrPolicyDatabase()
        .getCandidates()
        .forEach(
            candidate ->
                records.add(SymbolicSrPolicyRecord.fromCandidate(candidate, simplifyGuards)));
    getGuardedSrPolicyDatabase()
        .getContributions()
        .forEach(
            contribution ->
                records.add(SymbolicSrPolicyRecord.fromContribution(contribution, simplifyGuards)));
    records.sort(SymbolicSrPolicyRecord.ordering());
    return ImmutableList.copyOf(records);
  }

  /** Produces a deterministic pretty-JSON SR policy/candidate/forwarding report. */
  @Nonnull
  public String toSrPolicyJson() {
    return toSrPolicyJson(true);
  }

  /** Produces the SR report with exact guard expressions held by the stable database. */
  @Nonnull
  public String toRawSrPolicyJson() {
    return toSrPolicyJson(false);
  }

  /** Produces the versioned SR export with exact, solver-independent guard ASTs. */
  @Nonnull
  public String toSrPolicyExportJson() {
    return SymbolicSrPolicyExport.of(
            getAllSrPolicyRecords(false), getLinkFailureKeysByGuardVariable())
        .toJson();
  }

  /** Human-readable SR forwarding branches, matching {@code 0_symbolic_routes.txt}. */
  @Nonnull
  public String toSrPolicyReadableText() {
    return toSrPolicyReadableText(true, null);
  }

  /** Same table, restricted to SR endpoints that cover {@code destinations}. */
  @Nonnull
  public String toSrPolicyReadableTextForDestinations(Set<Prefix> destinations) {
    return toSrPolicyReadableText(true, destinations);
  }

  private String toSrPolicyReadableText(boolean simplifyGuards, Set<Prefix> destinations) {
    StringBuilder output = new StringBuilder();
    output.append(
        simplifyGuards
            ? "SR POLICY FORWARDING BRANCHES\n"
            : "SR POLICY CANDIDATES AND FORWARDING BRANCHES\n");
    appendSrPolicyTable(output, simplifyGuards, destinations);
    return output.toString();
  }

  private String toSrPolicyJson(boolean simplifyGuards) {
    try {
      return BatfishObjectMapper.writePrettyString(getAllSrPolicyRecords(simplifyGuards));
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize symbolic SR-policy report", e);
    }
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

  /** Returns every satisfiable MAIN contribution as an independent guarded forwarding branch. */
  @Nonnull
  public ImmutableList<SymbolicRibRecord> getMainForwardingBranches() {
    return getMainForwardingBranches(true);
  }

  @Nonnull
  private ImmutableList<SymbolicRibRecord> getMainForwardingBranches(boolean simplifyGuards) {
    List<SymbolicRibRecord> records = new ArrayList<>();
    _mainRibNetwork
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        candidate ->
                            rib.getContributionEntries(candidate.getSymbolicRoute().getKey())
                                .forEach(
                                    (id, branch) -> {
                                      if (branch.getSelectionGuard().isSatisfiable()) {
                                        records.add(
                                            SymbolicRibRecord.fromContribution(
                                                SymbolicRibRecord.Plane.MAIN,
                                                id,
                                                branch,
                                                simplifyGuards));
                                      }
                                    })));
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

  /** Returns the versioned, lossless control-plane transport model for downstream analysis. */
  @Nonnull
  public SymbolicControlPlaneExport toControlPlaneExport() {
    return SymbolicControlPlaneExport.from(this);
  }

  /** Produces the lossless machine-readable control-plane JSON integration contract. */
  @Nonnull
  public String toControlPlaneJson() {
    return toControlPlaneExport().toJson();
  }

  /** Produces a router/VRF report intended for direct human review. */
  @Nonnull
  public String toReadableText() {
    return toReadableText(true, null);
  }

  /** Produces a human-readable projection for routes that overlap the requested destinations. */
  @Nonnull
  public String toReadableTextForDestinations(Set<Prefix> destinations) {
    if (requireNonNull(destinations, "destinations must be provided").isEmpty()) {
      throw new IllegalArgumentException("destinations must not be empty");
    }
    return toReadableText(true, destinations);
  }

  /** Produces the same report with the exact guard expressions held by the stable RIBs. */
  @Nonnull
  public String toRawReadableText() {
    return toReadableText(false, null);
  }

  private String toReadableText(boolean simplifyGuards, Set<Prefix> destinations) {
    StringBuilder output = new StringBuilder("SYMBOLIC ROUTING INFORMATION BASE\n");
    output.append("Guards describe route availability and final selection conditions.\n");
    if (destinations != null) {
      output.append("Destination projection: ").append(new TreeSet<>(destinations)).append('\n');
    }
    output.append("\nMAIN RIB (guarded forwarding selections)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.MAIN, simplifyGuards, true, destinations);
    output.append("\nBGP LOC-RIB (protocol detail)\n");
    appendReadableTable(output, SymbolicRibRecord.Plane.BGP, simplifyGuards, false, destinations);
    output.append("\nIS-IS LEVEL-1 RIB (protocol detail)\n");
    appendReadableTable(
        output, SymbolicRibRecord.Plane.ISIS_L1, simplifyGuards, false, destinations);
    output.append("\nIS-IS LEVEL-2 RIB (protocol detail)\n");
    appendReadableTable(
        output, SymbolicRibRecord.Plane.ISIS_L2, simplifyGuards, false, destinations);
    output.append(
        simplifyGuards
            ? "\nSR POLICY FORWARDING BRANCHES\n"
            : "\nSR POLICY CANDIDATES AND FORWARDING BRANCHES\n");
    appendSrPolicyTable(output, simplifyGuards, destinations);
    return output.toString();
  }

  private void appendSrPolicyTable(
      StringBuilder output, boolean simplifyGuards, Set<Prefix> destinations) {
    if (simplifyGuards) {
      appendSimplifiedSrPolicyTable(output, destinations);
      return;
    }
    String commonFormat =
        "%-18s %-8s %-9s %-8s %-16s %-20s %-18s %-8s %-8s %-18s %-20s %-18s";
    output.append(
        String.format(
            commonFormat,
            "Kind",
            "Node",
            "VRF",
            "Color",
            "Endpoint",
            "Policy",
            "Candidate",
            "Pref",
            "Weight",
            "SegmentList",
            "Labels",
            "NextHops"));
    output.append(String.format(" %-24s %s%n", "AvailabilityGuard", "SelectionGuard"));
    output.append(
        "========================================================================================================================================================================\n");
    for (SymbolicSrPolicyRecord record : getAllSrPolicyRecords(simplifyGuards)) {
      if (!matchesSrEndpoint(record, destinations)) {
        continue;
      }
      String commonValues =
          String.format(
              commonFormat,
              record.getKind(),
              record.getNode(),
              record.getVrf(),
              record.getColor(),
              record.getEndpoint(),
              record.getPolicy(),
              record.getCandidate(),
              record.getPreference(),
              record.getWeight(),
              record.getSegmentList(),
              record.getLabels().isEmpty() ? "-" : record.getLabels(),
              record.getNextHops().isEmpty() ? "-" : record.getNextHops());
      output.append(commonValues);
      output.append(String.format(" %-24s", oneLine(record.getAvailabilityGuard())));
      output.append(String.format(" %s%n", oneLine(record.getSelectionGuard())));
    }
  }

  private void appendSimplifiedSrPolicyTable(StringBuilder output, Set<Prefix> destinations) {
    String format =
        "%-8s %-9s %-8s %-16s %-20s %-22s %-8s %-8s %-18s %-20s %-18s %s%n";
    output.append(
        String.format(
            format,
            "Node",
            "VRF",
            "Color",
            "Endpoint",
            "Policy",
            "Candidate",
            "Pref",
            "Weight",
            "SegmentList",
            "Labels",
            "NextHops",
            "SelectionGuard"));
    output.append(
        "========================================================================================================================================================================\n");
    for (SymbolicSrPolicyRecord record : getAllSrPolicyRecords(true)) {
      if (record.getKind() != SymbolicSrPolicyRecord.Kind.FORWARDING_BRANCH) {
        continue;
      }
      if (!matchesSrEndpoint(record, destinations)) {
        continue;
      }
      output.append(
          String.format(
              format,
              record.getNode(),
              record.getVrf(),
              record.getColor(),
              record.getEndpoint(),
              record.getPolicy(),
              record.getCandidate(),
              record.getPreference(),
              record.getWeight(),
              record.getSegmentList(),
              record.getLabels().isEmpty() ? "-" : record.getLabels(),
              record.getNextHops().isEmpty() ? "-" : record.getNextHops(),
              oneLine(record.getSelectionGuard())));
    }
  }

  private void appendReadableTable(
      StringBuilder output,
      SymbolicRibRecord.Plane plane,
      boolean simplifyGuards,
      boolean omitNeverSelected,
      Set<Prefix> destinations) {
    String pathHeader =
        plane == SymbolicRibRecord.Plane.MAIN ? "ForwardingPath" : "AdvertisementPath";
    String commonFormat = "%-8s %-9s %-18s %-10s %-8s %-5s %-10s %-16s %-18s";
    output.append(
        String.format(
            commonFormat,
            "Node",
            "VRF",
            "Network",
            "Protocol",
            "Metric",
            "AD",
            "NextHop",
            "NextHopIP",
            "NextHopInterface"));
    output.append(
        simplifyGuards
            ? String.format(" %-55s %s%n", "SelectionGuard", pathHeader)
            : String.format(
                " %-28s %-55s %s%n", "AvailabilityGuard", "SelectionGuard", pathHeader));
    output.append(
        "========================================================================================================================================================================\n");
    Iterable<SymbolicRibRecord> routes =
        plane == SymbolicRibRecord.Plane.MAIN
            ? getMainForwardingBranches(simplifyGuards)
            : getAllRoutes(simplifyGuards);
    for (SymbolicRibRecord route : routes) {
      if (route.getPlane() != plane) {
        continue;
      }
      if (!matchesDestination(route, destinations)) {
        continue;
      }
      if (omitNeverSelected && !route.getSelectionSatisfiable()) {
        continue;
      }
      String commonValues =
          String.format(
              commonFormat,
              route.getRouter(),
              route.getVrf(),
              route.getPrefix(),
              route.getProtocol(),
              route.getMetric(),
              route.getAdministrativeCost(),
              readableNextHopNode(route, plane),
              route.getNextHopIp(),
              route.getNextHopInterface());
      output.append(commonValues);
      if (!simplifyGuards) {
        output.append(String.format(" %-28s", oneLine(route.getAvailabilityGuard())));
      }
      output.append(
          String.format(
              " %-55s %s%n",
              oneLine(route.getSelectionGuard()),
              String.join(
                  " -> ",
                  plane == SymbolicRibRecord.Plane.MAIN
                      ? route.getForwardingPath()
                      : route.getRouterPath())));
    }
  }

  private static boolean matchesDestination(SymbolicRibRecord route, Set<Prefix> destinations) {
    if (destinations == null) {
      return true;
    }
    Prefix routePrefix = Prefix.parse(route.getPrefix());
    return destinations.stream()
        .anyMatch(
            destination ->
                routePrefix.containsPrefix(destination) || destination.containsPrefix(routePrefix));
  }

  private static boolean matchesSrEndpoint(
      SymbolicSrPolicyRecord record, Set<Prefix> destinations) {
    if (destinations == null) {
      return true;
    }
    return Ip.tryParse(record.getEndpoint())
        .map(
            endpoint ->
                destinations.stream().anyMatch(destination -> destination.containsIp(endpoint)))
        .orElse(false);
  }

  private static String readableNextHopNode(
      SymbolicRibRecord route, SymbolicRibRecord.Plane plane) {
    List<String> path =
        plane == SymbolicRibRecord.Plane.MAIN
            ? route.getForwardingPath()
            : route.getRouterPath();
    if (path.size() < 2) {
      return "null";
    }
    return plane == SymbolicRibRecord.Plane.MAIN
        ? path.get(1)
        : path.get(path.size() - 2);
  }

  private static String oneLine(String value) {
    return value.replaceAll("\\s+", " ").trim();
  }
}
