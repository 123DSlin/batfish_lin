package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.dataplane.protocols.StaticRouteHelper.shouldActivateNextHopIpRoute;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.dataplane.rib.Rib;

/** Symbolically lifts Batfish main-RIB LPM and static next-hop-IP activation semantics. */
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
    Map<SymbolicStaticRoute, RouteGuard> installed = new LinkedHashMap<>();
    boolean changed;
    int rounds = 0;
    do {
      changed = false;
      for (SymbolicStaticRoute route : routes) {
        GuardedRib<AnnotatedRoute<AbstractRoute>> rib = network.getRib(route.getRouter());
        RouteGuard guard = activationGuard(rib, route);
        RouteGuard previous = installed.get(route);
        if (previous != null && previous.isEquivalentTo(guard)) {
          continue;
        }
        installed.put(route, guard);
        network
            .getEngine()
            .converge(
                ImmutableList.of(
                    new SymbolicRouteSeed<>(
                            route.getMessageId(), route.getRouter(), widen(route.getRoute()), guard)
                        .toMessage()));
        changed = true;
      }
      rounds++;
      if (rounds > routes.size() + 1) {
        throw new IllegalStateException("static route activation did not reach a fixed point");
      }
    } while (changed);
    return ImmutableMap.copyOf(installed);
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
