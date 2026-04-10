package org.batfish.dataplane.ibdp;

import static org.batfish.common.topology.TopologyUtil.computeLayer2Topology;
import static org.batfish.common.topology.TopologyUtil.computeLayer3Topology;
import static org.batfish.common.topology.TopologyUtil.computeRawLayer3Topology;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.io.Writer;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.stream.Collectors;
import javax.annotation.Nonnull;
import org.batfish.common.topology.Layer1Edge;
import org.batfish.common.topology.Layer1Node;
import org.batfish.common.topology.Layer1Topology;
import org.batfish.common.topology.Layer2Topology;
import org.batfish.common.topology.TopologyUtil;
import org.batfish.common.topology.TunnelTopology;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpAdvertisement;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.Edge;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.GenericRib;
import org.batfish.datamodel.NetworkConfigurations;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.Topology;
import org.batfish.datamodel.bgp.BgpTopology;
import org.batfish.datamodel.eigrp.EigrpTopologyUtils;
import org.batfish.datamodel.ipsec.IpsecTopology;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.datamodel.ospf.OspfTopology;
import org.batfish.datamodel.ospf.OspfTopologyUtils;
import org.batfish.datamodel.vxlan.VxlanTopology;

/**
 * Enumerate physical edge failures (in raw layer-1 physical topology), run iBDP fixed-point
 * dataplane computation, and dump Main RIBs (all VRFs).
 *
 * <p>This utility is intentionally "in-memory": it does not require snapshots or storage.
 */
public final class FailureDataplaneEnumerator {

  public enum FailureMode {
    /** Enumerate failure sets of size exactly k. */
    EXACT_K,
    /** Enumerate failure sets of size 0..k. */
    AT_MOST_K
  }

  /**
   * A canonical (undirected) physical link identifier: two layer-1 nodes with stable ordering.
   * Selecting a link as "failed" implies both directed {@link Layer1Edge}s are removed/disabled.
   */
  public static final class PhysicalLink {
    private final Layer1Node _a;
    private final Layer1Node _b;

    private PhysicalLink(Layer1Node a, Layer1Node b) {
      // Canonical ordering for stable equality/hashCode
      if (compareNode(a, b) <= 0) {
        _a = a;
        _b = b;
      } else {
        _a = b;
        _b = a;
      }
    }

    public static PhysicalLink of(Layer1Node n1, Layer1Node n2) {
      return new PhysicalLink(n1, n2);
    }

    public Layer1Node getA() {
      return _a;
    }

    public Layer1Node getB() {
      return _b;
    }

    public String stableId() {
      return String.format(
          "%s:%s--%s:%s",
          _a.getHostname(), _a.getInterfaceName(), _b.getHostname(), _b.getInterfaceName());
    }

    @Override
    public boolean equals(Object o) {
      if (this == o) {
        return true;
      }
      if (!(o instanceof PhysicalLink)) {
        return false;
      }
      PhysicalLink that = (PhysicalLink) o;
      return _a.equals(that._a) && _b.equals(that._b);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_a, _b);
    }

    @Override
    public String toString() {
      return stableId();
    }

    private static int compareNode(Layer1Node x, Layer1Node y) {
      int c = x.getHostname().compareTo(y.getHostname());
      if (c != 0) {
        return c;
      }
      return x.getInterfaceName().compareTo(y.getInterfaceName());
    }
  }

  /** Result for one failure scenario. */
  public static final class ScenarioResult {
    private final @Nonnull FailureMode _mode;
    private final int _k;
    private final @Nonnull Set<PhysicalLink> _failedLinks;
    private final @Nonnull
        SortedMap<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>>
            _mainRibs;

    private ScenarioResult(
        FailureMode mode,
        int k,
        Set<PhysicalLink> failedLinks,
        SortedMap<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> mainRibs) {
      _mode = mode;
      _k = k;
      _failedLinks = ImmutableSet.copyOf(failedLinks);
      _mainRibs = mainRibs;
    }

    public FailureMode getMode() {
      return _mode;
    }

    public int getK() {
      return _k;
    }

    public Set<PhysicalLink> getFailedLinks() {
      return _failedLinks;
    }

    public SortedMap<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> getMainRibs() {
      return _mainRibs;
    }

    public String scenarioId() {
      if (_failedLinks.isEmpty()) {
        return "fail0";
      }
      String links =
          _failedLinks.stream()
              .sorted(Comparator.comparing(PhysicalLink::stableId))
              .map(PhysicalLink::stableId)
              .collect(Collectors.joining("__"));
      // Keep filename manageable; use hash suffix for uniqueness
      int h = links.hashCode();
      return String.format("fail%d_%08x", _failedLinks.size(), h);
    }
  }

  /**
   * Enumerate failures and dump Main RIBs to output directory.
   *
   * <p>This overload infers a candidate raw physical layer-1 topology directly from {@code configs}
   * by synthesizing layer-3 adjacencies and treating each L3 adjacency (interface-to-interface) as
   * a physical link for failure enumeration.
   *
   * <p>Note: real physical layer-1 data may not be present in configs. This method provides a
   * reasonable, self-contained default for in-memory experiments.
   */
  public static List<ScenarioResult> enumerateAndDumpMainRibs(
      @Nonnull Map<String, Configuration> configs,
      int k,
      @Nonnull FailureMode mode,
      @Nonnull Set<BgpAdvertisement> externalAdverts,
      @Nonnull Path outputDir) {
    return enumerateAndDumpMainRibs(
        configs, inferRawLayer1PhysicalTopologyFromConfigs(configs), k, mode, externalAdverts, outputDir);
  }

  /**
   * Enumerate failures and dump Main RIBs to output directory.
   *
   * <p>Failures are injected at raw physical L1. Additionally, for each failed link, both endpoint
   * interfaces are temporarily set to {@code active=false} (restored after computation), so that
   * downstream topology cleaning and protocol session computations see the interfaces as down.
   *
   * @param configs VI configurations (mutable; interface active flags will be toggled and restored)
   * @param rawLayer1PhysicalTopology base raw physical L1; failures are injected here
   * @param k maximum (or exact) number of failed links per scenario
   * @param mode EXACT_K or AT_MOST_K
   * @param externalAdverts external BGP advertisements (may be empty)
   * @param outputDir directory to write results; must exist or be creatable
   * @return list of scenario results (contains the main RIBs in-memory as well)
   */
  public static List<ScenarioResult> enumerateAndDumpMainRibs(
      @Nonnull Map<String, Configuration> configs,
      @Nonnull Optional<Layer1Topology> rawLayer1PhysicalTopology,
      int k,
      @Nonnull FailureMode mode,
      @Nonnull Set<BgpAdvertisement> externalAdverts,
      @Nonnull Path outputDir) {
    Objects.requireNonNull(configs, "configs must be non-null");
    Objects.requireNonNull(rawLayer1PhysicalTopology, "rawLayer1PhysicalTopology must be non-null");
    Objects.requireNonNull(mode, "mode must be non-null");
    Objects.requireNonNull(externalAdverts, "externalAdverts must be non-null");
    Objects.requireNonNull(outputDir, "outputDir must be non-null");
    if (k < 0) {
      throw new IllegalArgumentException("k must be >= 0");
    }

    try {
      Files.createDirectories(outputDir);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }

    NetworkConfigurations networkConfigurations = NetworkConfigurations.of(configs);
    // Ensure OSPF neighbor configs exist before computing OSPF topology.
    OspfTopologyUtils.initNeighborConfigs(networkConfigurations);

    List<PhysicalLink> candidateLinks = getCandidatePhysicalLinks(rawLayer1PhysicalTopology);
    int minSize = mode == FailureMode.EXACT_K ? k : 0;
    int maxSize = k;

    IncrementalBdpEngine engine = new IncrementalBdpEngine(new IncrementalDataPlaneSettings());
    List<ScenarioResult> results = new ArrayList<>();

    for (int size = minSize; size <= maxSize; size++) {
      enumerateCombinations(
          candidateLinks,
          size,
          failedLinks -> {
            ScenarioResult r =
                computeOneScenario(
                    engine,
                    configs,
                    rawLayer1PhysicalTopology,
                    failedLinks,
                    externalAdverts,
                    outputDir,
                    mode,
                    k);
            results.add(r);
          });
    }

    return results;
  }

  /**
   * Infer a raw physical layer-1 topology from {@code configs} only.
   *
   * <p>Implementation: synthesize the layer-3 topology (interface-to-interface edges inferred from
   * IP addressing), then treat each L3 edge as a candidate physical L1 edge between the same
   * interface endpoints, adding both directions.
   */
  private static Optional<Layer1Topology> inferRawLayer1PhysicalTopologyFromConfigs(
      Map<String, Configuration> configs) {
    Topology l3 = TopologyUtil.synthesizeL3Topology(configs);
    Set<String> presentStableIds = new HashSet<>();
    ImmutableSet.Builder<Layer1Edge> edges = ImmutableSet.builder();
    for (Edge e : l3.getEdges()) {
      Layer1Edge l1 = new Layer1Edge(e.getNode1(), e.getInt1(), e.getNode2(), e.getInt2());
      edges.add(l1);
      edges.add(l1.reverse());
        presentStableIds.add(PhysicalLink.of(l1.getNode1(), l1.getNode2()).stableId());
    }
    for (Layer1Edge extra : computeSupplementPtToPtLayer1Edges(configs, presentStableIds)) {
        edges.add(extra);
        edges.add(extra.reverse());
    }
    ImmutableSet<Layer1Edge> built = edges.build();
    if (built.isEmpty()) {
        return Optional.empty();
    }
      return Optional.of(new Layer1Topology(built));
  }
    /**   * Point-to-point links on {@code /30} or {@code /31} subnets: exactly one interface per end,<br/>   * distinct nodes, no shared IP. Skips links already recorded in {@code presentStableIds} and<br/>   * adds new stable ids there.<br/>   */
    private static List<Layer1Edge> computeSupplementPtToPtLayer1Edges(
            Map<String, Configuration> configs, Set<String> presentStableIds) {
        Map<Prefix, List<Interface>> byExactPrefix = new HashMap<>();
        for (Configuration c : configs.values()) {
            for (Interface iface : c.getAllInterfaces().values()) {
        if (!iface.getActive() || iface.isLoopback()) {
            continue;
        }
        if (Interface.TUNNEL_INTERFACE_TYPES.contains(iface.getInterfaceType())) {
            continue;
        }
        for (ConcreteInterfaceAddress addr : iface.getAllConcreteAddresses()) {
            Prefix p = addr.getPrefix();
            int len = p.getPrefixLength();
            if (len != Prefix.MAX_PREFIX_LENGTH - 2 && len != Prefix.MAX_PREFIX_LENGTH - 1) {
                continue;
            }
            byExactPrefix.computeIfAbsent(p, k -> new ArrayList<>()).add(iface);
        }
    }
    }
    List<Layer1Edge> out = new ArrayList<>();
        for (List<Interface> group : byExactPrefix.values()) {
            Map<String, Interface> unique = new LinkedHashMap<>();
            for (Interface iface : group) {
            String k = iface.getOwner().getHostname() + "\0" + iface.getName();
            unique.putIfAbsent(k, iface);
            }
            List<Interface> ifaces = new ArrayList<>(unique.values());
            if (ifaces.size() != 2) {
                continue;
            }
            Interface a = ifaces.get(0);
            Interface b = ifaces.get(1);
            if (a.getOwner() == b.getOwner()) {
                continue;
            }
            if (interfacesShareAnIpAddress(a, b)) {
                continue;
            }
            Layer1Edge forward =
            new Layer1Edge(
            a.getOwner().getHostname(), a.getName(), b.getOwner().getHostname(), b.getName());
            PhysicalLink pl = PhysicalLink.of(forward.getNode1(), forward.getNode2());
            if (presentStableIds.contains(pl.stableId())) {
                continue;
            }
            presentStableIds.add(pl.stableId());
            out.add(forward);
        }
        return out;
    }
    private static boolean interfacesShareAnIpAddress(Interface a, Interface b) {    for (ConcreteInterfaceAddress ia : a.getAllConcreteAddresses()) {
        for (ConcreteInterfaceAddress ib : b.getAllConcreteAddresses()) {
            if (ia.getIp().equals(ib.getIp())) {
                return true;
            }
        }
    }
        return false;



  }

  private static ScenarioResult computeOneScenario(
      IncrementalBdpEngine engine,
      Map<String, Configuration> configs,
      Optional<Layer1Topology> baseRawLayer1Physical,
      Set<PhysicalLink> failedLinks,
      Set<BgpAdvertisement> externalAdverts,
      Path outputDir,
      FailureMode mode,
      int k) {
    // Toggle interface active=false for endpoints, and restore in finally.
    Map<InterfaceKey, Boolean> priorActives = new HashMap<>();
    Set<Layer1Edge> failedDirectedEdges = new HashSet<>();
    for (PhysicalLink link : failedLinks) {
      failedDirectedEdges.add(new Layer1Edge(link.getA(), link.getB()));
      failedDirectedEdges.add(new Layer1Edge(link.getB(), link.getA()));
      priorActives.putAll(setInterfaceActive(configs, link.getA(), false));
      priorActives.putAll(setInterfaceActive(configs, link.getB(), false));
    }
    try {
      // Remove failed edges from raw physical L1.
      Optional<Layer1Topology> rawAfterFailure =
          baseRawLayer1Physical.map(
              l1 ->
                  new Layer1Topology(
                      l1.getGraph().edges().stream()
                          .filter(e -> !failedDirectedEdges.contains(e))
                          .collect(ImmutableSet.toImmutableSet())));

      // Clean raw -> physical (removes inactive interfaces and symmetrizes).
      Optional<Layer1Topology> physicalL1 =
          rawAfterFailure.map(l1 -> TopologyUtil.cleanLayer1PhysicalTopology(l1, configs));

      // Derive logical L1 from physical L1.
      Optional<Layer1Topology> logicalL1 =
          physicalL1.map(l1 -> TopologyUtil.computeLayer1LogicalTopology(l1, configs));

      // Derive initial L2 from logical L1 (ignore vxlan at this stage).
      Optional<Layer2Topology> l2 =
          logicalL1.map(l1 -> computeLayer2Topology(l1, VxlanTopology.EMPTY, configs));

      // Derive raw L3 from (raw physical, logical L1, L2) and then initial L3.
      Topology rawL3 = computeRawLayer3Topology(rawAfterFailure, logicalL1, l2, configs);
      Topology l3 = computeLayer3Topology(rawL3, ImmutableSet.of());

      // Compute protocol topologies from l3 (OSPF/ISIS/EIGRP). BGP is updated dynamically in iBDP.
      NetworkConfigurations networkConfigurations = NetworkConfigurations.of(configs);
      OspfTopology ospf = OspfTopologyUtils.computeOspfTopology(networkConfigurations, l3);
      IsisTopology isis = IsisTopology.initIsisTopology(configs, l3);

      TopologyContext tc =
          TopologyContext.builder()
              .setRawLayer1PhysicalTopology(rawAfterFailure)
              .setLayer1LogicalTopology(logicalL1)
              .setLayer2Topology(l2)
              .setLayer3Topology(l3)
              .setOspfTopology(ospf)
              .setIsisTopology(isis)
              .setEigrpTopology(EigrpTopologyUtils.initEigrpTopology(configs, l3))
              .setBgpTopology(BgpTopology.EMPTY)
              .setIpsecTopology(IpsecTopology.EMPTY)
              .setTunnelTopology(TunnelTopology.EMPTY)
              .setVxlanTopology(VxlanTopology.EMPTY)
              .build();

      DataPlane dp = engine.computeDataPlane(configs, tc, externalAdverts)._dataPlane;
      SortedMap<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> ribs =
              dp.getRibs();

      ScenarioResult result = new ScenarioResult(mode, k, failedLinks, ribs);
      dumpMainRibs(result, outputDir);
      return result;
    } finally {
      restoreInterfaceActive(configs, priorActives);
    }
  }

  private static void dumpMainRibs(ScenarioResult result, Path outputDir) {
    String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
    String dirName = String.format("failures_%s_k%d", result.getMode().name(), result.getK());
    Path dir = outputDir.resolve(dirName);
    try {
      Files.createDirectories(dir);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
    Path out = dir.resolve(String.format("%s_%s_main_rib.txt", result.scenarioId(), timestamp));
    try (Writer w = Files.newBufferedWriter(out, StandardCharsets.UTF_8)) {
      dumpMainRibsText(result, w);
    } catch (IOException e) {
      throw new UncheckedIOException(e);
    }
  }

  private static void dumpMainRibsText(ScenarioResult result, Writer w) throws IOException {
    w.write(
        String.format(
            "mode=%s k=%d failedLinks=%d%n",
            result.getMode(), result.getK(), result.getFailedLinks().size()));
    for (PhysicalLink link :
        result.getFailedLinks().stream()
            .sorted(Comparator.comparing(PhysicalLink::stableId))
            .collect(ImmutableList.toImmutableList())) {
      w.write(String.format("FAILED %s%n", link.stableId()));
    }
    w.write(System.lineSeparator());

    SortedMap<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> ribs =
        new TreeMap<>(result.getMainRibs());
      // Build a best-effort map from interface IP (/32 local routes) to node name, so we can display
      // the BGP next-hop "node" in a compact way.
      // the BGP next-hop "node" in a compact way.
      Map<String, String> ipToNode = new HashMap<>();
      for (Map.Entry<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> nodeEntry :
              ribs.entrySet()) {
          String node = nodeEntry.getKey();
          for (GenericRib<AnnotatedRoute<AbstractRoute>> rib : nodeEntry.getValue().values()) {
              for (AnnotatedRoute<AbstractRoute> ar : rib.getTypedRoutes()) {
                  AbstractRoute r = ar.getAbstractRoute();
                  if (r.getProtocol().protocolName().equalsIgnoreCase("local")
                          && r.getNetwork() != null
                          && r.getNetwork().getPrefixLength() == Prefix.MAX_PREFIX_LENGTH) {
                      ipToNode.put(r.getNetwork().getStartIp().toString(), node);
                  }
              }
          }
      }

        w.write(
                String.format(
                        "%-12s %-8s %-20s %-10s %-16s %-26s %-8s %-8s %-8s %-8s%n",
                        "Node",
                        "VRF",
                        "Network",
                        "Protocol",
                        "NextHopIP",
                        "NextHopInterface",
                        "NextHop",
                        "Metric",
                        "AD",
                        "Tag"));
      w.write(String.format("%s%n", repeatChar('=', 126)));

    for (Map.Entry<String, SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>>> nodeEntry :
        ribs.entrySet()) {
      String node = nodeEntry.getKey();
      SortedMap<String, GenericRib<AnnotatedRoute<AbstractRoute>>> vrfs =
          new TreeMap<>(nodeEntry.getValue());
      for (Map.Entry<String, GenericRib<AnnotatedRoute<AbstractRoute>>> vrfEntry : vrfs.entrySet()) {
        String vrf = vrfEntry.getKey();
        GenericRib<AnnotatedRoute<AbstractRoute>> rib = vrfEntry.getValue();
          List<AnnotatedRoute<AbstractRoute>> routes = new ArrayList<>(rib.getTypedRoutes());
          routes.sort(FailureDataplaneEnumerator::compareAnnotatedRoutesForDump);
        for (AnnotatedRoute<AbstractRoute> ar : routes) {
          AbstractRoute r = ar.getAbstractRoute();
          Prefix p = r.getNetwork();
          String proto = r.getProtocol().protocolName();
          String nhIp = r.getNextHopIp() == null ? "null" : r.getNextHopIp().toString();
          String nhIf = r.getNextHopInterface() == null ? "null" : r.getNextHopInterface();
          String nhNode;
          if (r.getNextHopIp() == null) {
              nhNode = "null";
          } else {
              String candidate = ipToNode.get(r.getNextHopIp().toString());
              nhNode = candidate == null ? "null" : candidate;
          }
          String metric = String.valueOf(r.getMetric());
          String ad = String.valueOf(r.getAdministrativeCost());
          String tag =
              r.getTag() == org.batfish.datamodel.Route.UNSET_ROUTE_TAG
                  ? "-"
                  : String.valueOf(r.getTag());
          w.write(
              String.format(
                     " %-12s %-8s %-20s %-10s %-16s %-26s %-8s %-8s %-8s %-8s%n",
                      node, vrf, p, proto, nhIp, nhIf, nhNode, metric, ad, tag));
        }
      }
    }
  }

  /** Stable sort order for dumping main RIB rows (Java-8-friendly, no Comparator.comparing). */
  private static int compareAnnotatedRoutesForDump(
    AnnotatedRoute<AbstractRoute> a, AnnotatedRoute<AbstractRoute> b) {
      int c = a.getNetwork().compareTo(b.getNetwork());
      if (c != 0) {
          return c;
      }
      c = a.getAbstractRoute()
          .getProtocol()
          .protocolName()
          .compareTo(b.getAbstractRoute().getProtocol().protocolName());
      if (c != 0) {
          return c;
      }
      c = String.valueOf(a.getAbstractRoute().getNextHopIp())
          .compareTo(String.valueOf(b.getAbstractRoute().getNextHopIp()));
      if (c != 0) {
          return c;
      }
        return String.valueOf(a.getAbstractRoute().getNextHopInterface())
            .compareTo(String.valueOf(b.getAbstractRoute().getNextHopInterface()));
    }
  private static String repeatChar(char c, int count) {
    StringBuilder sb = new StringBuilder(count);
    for (int i = 0; i < count; i++) {
      sb.append(c);
    }
    return sb.toString();
  }

  private static List<PhysicalLink> getCandidatePhysicalLinks(Optional<Layer1Topology> rawL1) {
    if (!rawL1.isPresent()) {
      return ImmutableList.of();
    }
    Set<PhysicalLink> links = new HashSet<>();
    for (Layer1Edge e : rawL1.get().getGraph().edges()) {
      links.add(PhysicalLink.of(e.getNode1(), e.getNode2()));
    }
    return links.stream()
        .sorted(Comparator.comparing(PhysicalLink::stableId))
        .collect(ImmutableList.toImmutableList());
  }

  /**
   * Enumerate all combinations of {@code choose} elements from {@code items}, calling {@code sink}
   * for each chosen set.
   */
  private static void enumerateCombinations(
      List<PhysicalLink> items, int choose, java.util.function.Consumer<Set<PhysicalLink>> sink) {
    if (choose < 0 || choose > items.size()) {
      return;
    }
    backtrack(items, choose, 0, new ArrayList<>(), sink);
  }

  private static void backtrack(
      List<PhysicalLink> items,
      int choose,
      int start,
      List<PhysicalLink> acc,
      java.util.function.Consumer<Set<PhysicalLink>> sink) {
    if (acc.size() == choose) {
      sink.accept(ImmutableSet.copyOf(acc));
      return;
    }
    int remaining = choose - acc.size();
    for (int i = start; i <= items.size() - remaining; i++) {
      acc.add(items.get(i));
      backtrack(items, choose, i + 1, acc, sink);
      acc.remove(acc.size() - 1);
    }
  }

  private static final class InterfaceKey {
    private final String _hostname;
    private final String _iface;

    private InterfaceKey(String hostname, String iface) {
      _hostname = hostname;
      _iface = iface;
    }

    static InterfaceKey of(Layer1Node n) {
      return new InterfaceKey(n.getHostname(), n.getInterfaceName());
    }

    @Override
    public boolean equals(Object o) {
      if (this == o) {
        return true;
      }
      if (!(o instanceof InterfaceKey)) {
        return false;
      }
      InterfaceKey that = (InterfaceKey) o;
      return _hostname.equals(that._hostname) && _iface.equals(that._iface);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_hostname, _iface);
    }
  }

  private static Map<InterfaceKey, Boolean> setInterfaceActive(
      Map<String, Configuration> configs, Layer1Node node, boolean active) {
    Configuration c = configs.get(node.getHostname());
    if (c == null) {
      return java.util.Collections.emptyMap();
    }
    org.batfish.datamodel.Interface iface = c.getAllInterfaces().get(node.getInterfaceName());
    if (iface == null) {
      return java.util.Collections.emptyMap();
    }
    InterfaceKey k = InterfaceKey.of(node);
    boolean prior = iface.getActive();
    iface.setActive(active);
    return java.util.Collections.singletonMap(k, prior);
  }

  private static void restoreInterfaceActive(
      Map<String, Configuration> configs, Map<InterfaceKey, Boolean> priorActives) {
    priorActives.forEach(
        (k, prior) -> {
          Configuration c = configs.get(k._hostname);
          if (c == null) {
            return;
          }
          org.batfish.datamodel.Interface iface = c.getAllInterfaces().get(k._iface);
          if (iface == null) {
            return;
          }
          iface.setActive(prior);
        });
  }

  private FailureDataplaneEnumerator() {}
}

