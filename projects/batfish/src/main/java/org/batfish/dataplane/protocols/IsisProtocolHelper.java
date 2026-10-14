package org.batfish.dataplane.protocols;

import static com.google.common.base.MoreObjects.firstNonNull;
import static org.batfish.datamodel.Route.UNSET_ROUTE_NEXT_HOP_IP;

import com.google.common.collect.ImmutableSet;
import java.util.Optional;
import java.util.Set;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisInterfaceMode;
import org.batfish.datamodel.isis.IsisLevel;
import org.batfish.datamodel.isis.IsisProcess;
import org.batfish.datamodel.routing_policy.Environment.Direction;
import org.batfish.datamodel.routing_policy.RoutingPolicy;
import org.batfish.dataplane.rib.RibDelta;

/** Helper class that implements various IS-IS protocol logic. */
public class IsisProtocolHelper {

  /**
   * Generate the prefixes originated into IS-IS by {@code iface} at {@code level}.
   *
   * <p>This is the shared concrete/symbolic definition of interface-prefix origination. A passive
   * interface originates its prefixes with metric {@code 0}; an active interface uses its
   * configured level cost, or {@link IsisRoute#DEFAULT_METRIC} when no cost is configured. Returns
   * an empty set when the interface is not enabled at the requested level.
   */
  @Nonnull
  public static Set<IsisRoute> generateInterfaceRoutes(
      @Nonnull Configuration configuration,
      @Nonnull IsisProcess process,
      @Nonnull Interface iface,
      @Nonnull IsisLevel level) {
    if (level == IsisLevel.LEVEL_1_2) {
      throw new IllegalArgumentException("interface routes require one IS-IS level");
    }
    IsisInterfaceLevelSettings levelSettings = getInterfaceLevelSettings(iface, level);
    if (levelSettings == null) {
      return ImmutableSet.of();
    }
    RoutingProtocol protocol =
        level == IsisLevel.LEVEL_1 ? RoutingProtocol.ISIS_L1 : RoutingProtocol.ISIS_L2;
    long metric =
        levelSettings.getMode() == IsisInterfaceMode.PASSIVE
            ? 0L
            : firstNonNull(levelSettings.getCost(), IsisRoute.DEFAULT_METRIC);
    int admin = protocol.getDefaultAdministrativeCost(configuration.getConfigurationFormat());
    ImmutableSet.Builder<IsisRoute> routes = ImmutableSet.builder();
    iface
        .getAllConcreteAddresses()
        .forEach(
            address ->
                routes.add(
                    IsisRoute.builder()
                        .setAdmin(admin)
                        .setArea(process.getNetAddress().getAreaIdString())
                        .setLevel(level)
                        .setMetric(metric)
                        .setNetwork(address.getPrefix())
                        .setNextHopIp(address.getIp())
                        .setProtocol(protocol)
                        .setSystemId(process.getNetAddress().getSystemIdString())
                        .build()));
    return routes.build();
  }

  /**
   * Generate the Level-1 attached default originated by a non-overloaded L1/L2 router.
   *
   * <p>Returns empty for a router that does not run both levels or is overloaded.
   */
  @Nonnull
  public static Optional<IsisRoute> generateAttachedDefaultRoute(
      @Nonnull Configuration configuration, @Nonnull IsisProcess process) {
    if (process.getLevel1() == null || process.getLevel2() == null || process.getOverload()) {
      return Optional.empty();
    }
    return Optional.of(
        IsisRoute.builder()
            .setAdmin(
                RoutingProtocol.ISIS_L1.getDefaultAdministrativeCost(
                    configuration.getConfigurationFormat()))
            .setArea(process.getNetAddress().getAreaIdString())
            .setAttach(true)
            .setLevel(IsisLevel.LEVEL_1)
            .setMetric(0L)
            .setNetwork(Prefix.ZERO)
            .setNextHopIp(UNSET_ROUTE_NEXT_HOP_IP)
            .setProtocol(RoutingProtocol.ISIS_L1)
            .setSystemId(process.getNetAddress().getSystemIdString())
            .build());
  }

  /**
   * Apply Batfish's single-hop IS-IS import transformation at {@code receiverInterface}.
   *
   * <p>The route keeps its level and protocol, gains the receiver's directed interface cost, uses
   * {@code nextHopIp}, receives the platform-specific administrative cost, and becomes routing.
   * Returns empty when the receiving interface is not active at the route's level.
   */
  @Nonnull
  public static Optional<IsisRoute> importRoute(
      @Nonnull IsisRoute neighborRoute,
      @Nonnull Configuration receiverConfiguration,
      @Nonnull Interface receiverInterface,
      @Nonnull Ip nextHopIp) {
    IsisInterfaceLevelSettings levelSettings =
        getInterfaceLevelSettings(receiverInterface, neighborRoute.getLevel());
    if (levelSettings == null || levelSettings.getMode() != IsisInterfaceMode.ACTIVE) {
      return Optional.empty();
    }
    long incrementalMetric = firstNonNull(levelSettings.getCost(), IsisRoute.DEFAULT_METRIC);
    int admin =
        neighborRoute
            .getProtocol()
            .getDefaultAdministrativeCost(receiverConfiguration.getConfigurationFormat());
    return Optional.of(
        neighborRoute.toBuilder()
            .setAdmin(admin)
            .setLevel(neighborRoute.getLevel())
            .setMetric(neighborRoute.getMetric() + incrementalMetric)
            .setNextHopIp(nextHopIp)
            .setNonRouting(false)
            .build());
  }

  @Nullable
  private static IsisInterfaceLevelSettings getInterfaceLevelSettings(
      Interface iface, IsisLevel level) {
    if (iface.getIsis() == null) {
      return null;
    }
    if (level == IsisLevel.LEVEL_1) {
      return iface.getIsis().getLevel1();
    }
    if (level == IsisLevel.LEVEL_2) {
      return iface.getIsis().getLevel2();
    }
    return null;
  }

  /**
   * Convert a level-1 IS-IS route to a level-2 IS-IS route. All route attributes except
   * level/protocol and the admin distance remain unchanged.
   *
   * @param route the route to convert
   * @param l2Admin the new L2 admin distance to use.
   * @return an optional of {@link IsisRoute}. It will be empty if the route given is not level 1 or
   *     has its down bit set.
   */
  public static Optional<IsisRoute> convertRouteLevel1ToLevel2(
      IsisRoute route, RoutingProtocol l2Protocol, int l2Admin) {
    if (route.getLevel() != IsisLevel.LEVEL_1 || route.getAttach() || route.getDown()) {
      return Optional.empty();
    }
    return Optional.of(
        route.toBuilder()
            .setAdmin(l2Admin)
            .setLevel(IsisLevel.LEVEL_2)
            .setProtocol(l2Protocol)
            .build());
  }

  @Nonnull
  public static RibDelta<IsisRoute> setOverloadOnAllRoutes(@Nonnull RibDelta<IsisRoute> delta) {

    RibDelta.Builder<IsisRoute> deltaWithOverloadTrue = RibDelta.builder();
    delta
        .getActions()
        .forEach(
            ra -> {
              IsisRoute newRoute = ra.getRoute().toBuilder().setOverload(true).build();
              if (ra.isWithdrawn()) {
                deltaWithOverloadTrue.remove(newRoute, ra.getReason());
              } else {
                deltaWithOverloadTrue.add(newRoute);
              }
            });
    return deltaWithOverloadTrue.build();
  }

  /**
   * Given an {@link AbstractRoute}, run it through IS-IS outbound transformations and export
   * routing policy.
   *
   * @return Transformed {@link IsisRoute} if {@code exportCandidate} passes the IS-IS export
   *     policy; otherwise {@code null}.
   */
  @Nullable
  public static IsisRoute exportNonIsisRouteToIsis(
      @Nonnull AnnotatedRoute<AbstractRoute> exportCandidate,
      @Nonnull IsisProcess process,
      boolean isLevel1,
      Configuration c) {
    // Get export policy if there is one
    RoutingPolicy exportPolicy =
        Optional.ofNullable(process.getExportPolicy())
            .map(policyName -> c.getRoutingPolicies().get(policyName))
            .orElse(null);
    if (exportPolicy == null) {
      // Export policy is undefined or not configured
      return null;
    }
    // Process transformed outgoing route through the export policy
    IsisRoute.Builder transformedOutgoingRouteBuilder =
        convertNonIsisRouteToIsisRoute(exportCandidate.getRoute(), process, isLevel1, c);
    boolean policyAcceptsRoute =
        exportPolicy.process(exportCandidate, transformedOutgoingRouteBuilder, Direction.OUT);

    // If route was accepted by export policy, return it
    return policyAcceptsRoute ? transformedOutgoingRouteBuilder.build() : null;
  }

  /**
   * Convert a non-ISIS route to an {@link IsisRoute.Builder}.
   *
   * <p>Intended for converting main RIB routes into their IS-IS equivalents before passing {@code
   * route} to the export policy.
   *
   * <p>Sets network, admin, metric, area, tag, protocol, level, overload, system ID, and nonRouting
   * (to true, should be cleared on import). Does not set next hop IP, attach, or down.
   */
  @Nonnull
  public static IsisRoute.Builder convertNonIsisRouteToIsisRoute(
      AbstractRoute route, IsisProcess process, boolean isLevel1, Configuration c) {
    assert !(route instanceof IsisRoute);
    RoutingProtocol protocol = isLevel1 ? RoutingProtocol.ISIS_EL1 : RoutingProtocol.ISIS_EL2;
    return IsisRoute.builder()
        .setNetwork(route.getNetwork())
        .setAdmin(protocol.getDefaultAdministrativeCost(c.getConfigurationFormat()))
        .setMetric(route.getMetric())
        .setArea(process.getNetAddress().getAreaIdString())
        .setTag(route.getTag())
        .setProtocol(protocol)
        .setLevel(isLevel1 ? IsisLevel.LEVEL_1 : IsisLevel.LEVEL_2)
        .setOverload(process.getOverload())
        .setNextHopIp(UNSET_ROUTE_NEXT_HOP_IP)
        .setSystemId(process.getNetAddress().getSystemIdString())
        .setNonRouting(true);
  }
}
