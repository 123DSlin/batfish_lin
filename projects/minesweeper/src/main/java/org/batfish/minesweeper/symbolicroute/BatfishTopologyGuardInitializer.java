package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SortedSet;
import java.util.TreeSet;
import javax.annotation.Nonnull;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Prefix;

/** Derives stable link guards from parsed Batfish interface topology. */
public final class BatfishTopologyGuardInitializer {

  private BatfishTopologyGuardInitializer() {}

  /**
   * Returns guards keyed by {@code hostname:interface}. A point-to-point link is named after its
   * sorted endpoints (for example {@code r1_r4}). Unsupported ambiguous topologies are rejected.
   */
  @Nonnull
  public static ImmutableMap<String, RouteGuard> inferInterfaceGuards(
      Map<String, Configuration> configurations, Z3RouteGuardFactory guardFactory) {
    TopologyLinkGuards topology = inferTopology(configurations, guardFactory);
    ImmutableMap.Builder<String, RouteGuard> guards = ImmutableMap.builder();
    topology
        .getKeysByEndpoint()
        .forEach((endpoint, key) -> guards.put(endpoint, topology.getGuardsByKey().get(key)));
    return guards.build();
  }

  /** Returns canonical identities and up-guards for every inferred point-to-point link endpoint. */
  @Nonnull
  public static TopologyLinkGuards inferTopology(
      Map<String, Configuration> configurations, Z3RouteGuardFactory guardFactory) {
    requireNonNull(configurations, "configurations must be provided");
    requireNonNull(guardFactory, "guardFactory must be provided");
    Map<Prefix, List<String>> endpointsByPrefix = new LinkedHashMap<>();
    for (Configuration configuration : configurations.values()) {
      for (Interface iface : configuration.getAllInterfaces().values()) {
        for (ConcreteInterfaceAddress address : iface.getAllConcreteAddresses()) {
          endpointsByPrefix
              .computeIfAbsent(address.getPrefix(), unused -> new ArrayList<>())
              .add(configuration.getHostname() + ":" + iface.getName());
        }
      }
    }

    Map<Prefix, LinkFailureKey> failureKeys = new LinkedHashMap<>();
    Map<LinkFailureKey, Integer> keyCounts = new LinkedHashMap<>();
    endpointsByPrefix.forEach(
        (prefix, endpoints) -> {
          SortedSet<String> routers = new TreeSet<>();
          endpoints.forEach(endpoint -> routers.add(endpoint.substring(0, endpoint.indexOf(':'))));
          if (routers.size() == 2) {
            LinkFailureKey key = LinkFailureKey.of(routers.first(), routers.last());
            failureKeys.put(prefix, key);
            keyCounts.merge(key, 1, Integer::sum);
          } else if (routers.size() > 2) {
            throw new IllegalArgumentException(
                "Minesweeper internal-link failures do not represent shared multi-access segments");
          }
        });

    Map<String, LinkFailureKey> keysByEndpoint = new LinkedHashMap<>();
    Map<LinkFailureKey, RouteGuard> guardsByKey = new LinkedHashMap<>();
    endpointsByPrefix.forEach(
        (prefix, endpoints) -> {
          LinkFailureKey failureKey = failureKeys.get(prefix);
          if (failureKey == null) {
            return;
          }
          if (keyCounts.get(failureKey) != 1) {
            throw new IllegalArgumentException(
                "Minesweeper currently collapses parallel links into one router-pair failure");
          }
          RouteGuard guard = guardFactory.variable(failureKey.guardName());
          guardsByKey.put(failureKey, guard);
          endpoints.forEach(endpoint -> keysByEndpoint.put(endpoint, failureKey));
        });
    return new TopologyLinkGuards(keysByEndpoint, guardsByKey);
  }
}
