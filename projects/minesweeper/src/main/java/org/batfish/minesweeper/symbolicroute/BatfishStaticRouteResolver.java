package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.dataplane.protocols.StaticRouteHelper.shouldActivateNextHopIpRoute;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.dataplane.rib.Rib;

/**
 * Symbolically lifts Batfish main-RIB LPM and static next-hop-IP activation semantics.
 *
 * <p>A concrete {@link Rib#longestPrefixMatch} call is used only as a semantic oracle. It cannot
 * replace symbolic LPM: an activating shorter prefix is explicitly guarded by the negation of every
 * available longer-prefix match, including longer matches that cannot themselves activate the
 * static route.
 */
public final class BatfishStaticRouteResolver {

  private BatfishStaticRouteResolver() {}

  /**
   * Resolves next-hop-IP static routes to a fixed point and installs them as local contributions.
   *
   * <p>The concrete route is never reconstructed: every activation decision is delegated to
   * Batfish's {@link Rib} and {@link org.batfish.dataplane.protocols.StaticRouteHelper}. This loop
   * only lifts those decisions over symbolic guards. Non-recursive static routes must be supplied
   * as ordinary seeds, matching Batfish {@code VirtualRouter.initStaticRibs}, which activates them
   * unconditionally.
   */
  @Nonnull
  public static ImmutableMap<SymbolicStaticRoute, RouteGuard> resolveToFixedPoint(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network,
      Iterable<SymbolicStaticRoute> staticRoutes) {
    requireNonNull(network, "network must be provided");
    List<SymbolicStaticRoute> routes =
        ImmutableList.copyOf(requireNonNull(staticRoutes, "staticRoutes must be provided"));
    validateInputs(network, routes);

    // A resolution run owns these contributions. Remove stale results first so activation is
    // computed from the caller's non-recursive initial RIB, as VirtualRouter does each iteration.
    List<SymbolicRouteContributionId> ownedContributions =
        routes.stream()
            .map(BatfishStaticRouteResolver::contributionId)
            .collect(Collectors.toList());
    network.getEngine().withdraw(ownedContributions);

    Map<SymbolicStaticRoute, RouteGuard> current = falseState(routes);
    List<Map<SymbolicStaticRoute, RouteGuard>> history = new ArrayList<>();
    history.add(current);
    try {
      while (true) {
        // Synchronous round: compute every guard from one RIB snapshot before mutating the engine.
        Map<SymbolicStaticRoute, RouteGuard> next = computeRound(network, routes);
        if (equivalentState(current, next)) {
          return ImmutableMap.copyOf(next);
        }
        if (history.stream().anyMatch(old -> equivalentState(old, next))) {
          throw new IllegalStateException("static route activation entered a semantic guard cycle");
        }
        ImmutableList.Builder<SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>>> updates =
            ImmutableList.builder();
        for (SymbolicStaticRoute route : routes) {
          if (!current.get(route).isEquivalentTo(next.get(route))) {
            updates.add(
                new SymbolicRouteSeed<>(
                        route.getContributionMessageId(),
                        route.getRouter(),
                        widen(route.getRoute()),
                        next.get(route))
                    .toMessage());
          }
        }
        network.getEngine().converge(updates.build());
        current = next;
        history.add(current);
      }
    } catch (RuntimeException failure) {
      // Resolution is all-or-nothing with respect to its derived static contributions.
      network.getEngine().withdraw(ownedContributions);
      throw failure;
    }
  }

  private static void validateInputs(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network,
      List<SymbolicStaticRoute> routes) {
    Set<SymbolicRouteContributionId> identities = new HashSet<>();
    for (SymbolicStaticRoute route : routes) {
      network.getRib(route.getRouter());
      if (!(route.getRoute().getRoute().getNextHop() instanceof NextHopIp)) {
        throw new IllegalArgumentException(
            "Batfish recursive activation requires a next-hop-IP route");
      }
      if (!identities.add(contributionId(route))) {
        throw new IllegalArgumentException("duplicate static route contribution identity");
      }
      SymbolicRouteKey key =
          new SymbolicRouteKey(
              route.getRouter(), route.getRoute().getSourceVrf(), widen(route.getRoute()));
      Set<SymbolicRouteContributionId> existing =
          network.getRib(route.getRouter()).getContributionIds(key);
      if (existing.stream().anyMatch(id -> !id.equals(contributionId(route)))) {
        throw new IllegalArgumentException(
            "recursive static candidate is already installed by an unowned contribution");
      }
    }
  }

  private static Map<SymbolicStaticRoute, RouteGuard> falseState(List<SymbolicStaticRoute> routes) {
    Map<SymbolicStaticRoute, RouteGuard> state = new LinkedHashMap<>();
    for (SymbolicStaticRoute route : routes) {
      RouteGuard configured = route.getConfigurationGuard();
      state.put(route, configured.and(configured.not()).simplify());
    }
    return state;
  }

  private static Map<SymbolicStaticRoute, RouteGuard> computeRound(
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> network,
      List<SymbolicStaticRoute> routes) {
    Map<SymbolicStaticRoute, RouteGuard> state = new LinkedHashMap<>();
    for (SymbolicStaticRoute route : routes) {
      state.put(route, activationGuard(network.getRib(route.getRouter()), route));
    }
    return state;
  }

  private static boolean equivalentState(
      Map<SymbolicStaticRoute, RouteGuard> left, Map<SymbolicStaticRoute, RouteGuard> right) {
    if (left.size() != right.size()) {
      return false;
    }
    for (Map.Entry<SymbolicStaticRoute, RouteGuard> entry : left.entrySet()) {
      RouteGuard other = right.get(entry.getKey());
      if (other == null || !entry.getValue().isEquivalentTo(other)) {
        return false;
      }
    }
    return true;
  }

  private static SymbolicRouteContributionId contributionId(SymbolicStaticRoute route) {
    return new SymbolicRouteContributionId(
        route.getContributionMessageId(), route.getRouter(), route.getRouter());
  }

  /** Computes the activation guard for one next-hop-IP static route. */
  @Nonnull
  public static RouteGuard activationGuard(
      GuardedRib<AnnotatedRoute<AbstractRoute>> symbolicRib, SymbolicStaticRoute symbolicStatic) {
    requireNonNull(symbolicRib, "symbolicRib must be provided");
    requireNonNull(symbolicStatic, "symbolicStatic must be provided");
    StaticRoute staticRoute = symbolicStatic.getRoute().getRoute();
    if (!(staticRoute.getNextHop() instanceof NextHopIp)) {
      throw new IllegalArgumentException(
          "Batfish recursive activation requires a next-hop-IP route");
    }
    Ip nextHopIp = ((NextHopIp) staticRoute.getNextHop()).getIp();
    String vrf = symbolicStatic.getRoute().getSourceVrf();
    RouteGuard configured = symbolicStatic.getConfigurationGuard();
    RouteGuard reachable = configured.and(configured.not()).simplify();
    List<GuardedRibEntry<AnnotatedRoute<AbstractRoute>>> matching = new ArrayList<>();
    for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry : symbolicRib.getEntries()) {
      if (!entry.getSymbolicRoute().getKey().getVrf().equals(vrf)
          || !entry.getSelectionGuard().isSatisfiable()
          || !batfishMatches(entry, nextHopIp)) {
        continue;
      }
      matching.add(entry);
    }
    for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> candidate : matching) {
      if (!batfishCanActivateFrom(staticRoute, candidate, nextHopIp)) {
        continue;
      }
      RouteGuard candidateIsLongest = candidate.getSelectionGuard();
      for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> other : matching) {
        if (candidate == other || samePrefix(candidate, other)) {
          continue;
        }
        if (batfishPrefersPrefix(other, candidate, nextHopIp)) {
          candidateIsLongest = candidateIsLongest.and(other.getSelectionGuard().not());
        }
      }
      reachable = reachable.or(candidateIsLongest).simplify();
    }
    return configured.and(reachable).simplify();
  }

  private static boolean batfishCanActivateFrom(
      StaticRoute staticRoute, GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry, Ip nextHopIp) {
    Rib oracle = new Rib();
    oracle.mergeRoute(entry.getSymbolicRoute().getRoute());
    return !oracle.longestPrefixMatch(nextHopIp).isEmpty()
        && shouldActivateNextHopIpRoute(staticRoute, oracle);
  }

  private static boolean batfishMatches(
      GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry, Ip nextHopIp) {
    Rib oracle = new Rib();
    oracle.mergeRoute(entry.getSymbolicRoute().getRoute());
    return !oracle.longestPrefixMatch(nextHopIp).isEmpty();
  }

  private static boolean samePrefix(
      GuardedRibEntry<AnnotatedRoute<AbstractRoute>> left,
      GuardedRibEntry<AnnotatedRoute<AbstractRoute>> right) {
    return left.getSymbolicRoute()
        .getKey()
        .getNetwork()
        .equals(right.getSymbolicRoute().getKey().getNetwork());
  }

  /**
   * Uses Batfish's prefix trie to decide whether {@code possibleLonger} dominates {@code route}.
   */
  private static boolean batfishPrefersPrefix(
      GuardedRibEntry<AnnotatedRoute<AbstractRoute>> possibleLonger,
      GuardedRibEntry<AnnotatedRoute<AbstractRoute>> route,
      Ip nextHopIp) {
    Rib oracle = new Rib();
    oracle.mergeRoute(possibleLonger.getSymbolicRoute().getRoute());
    oracle.mergeRoute(route.getSymbolicRoute().getRoute());
    java.util.Set<AnnotatedRoute<AbstractRoute>> matches = oracle.longestPrefixMatch(nextHopIp);
    return !matches.isEmpty()
        && matches.stream()
            .allMatch(
                matched ->
                    matched
                        .getNetwork()
                        .equals(possibleLonger.getSymbolicRoute().getKey().getNetwork()));
  }

  private static AnnotatedRoute<AbstractRoute> widen(AnnotatedRoute<StaticRoute> route) {
    return new AnnotatedRoute<>(route.getRoute(), route.getSourceVrf());
  }
}
