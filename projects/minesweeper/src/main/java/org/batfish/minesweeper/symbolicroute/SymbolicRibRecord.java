package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.Comparator;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;
import org.batfish.datamodel.route.nh.NextHop;
import org.batfish.datamodel.route.nh.NextHopInterface;
import org.batfish.datamodel.route.nh.NextHopIp;

/** Serializable, protocol-neutral view of one final guarded RIB candidate. */
public final class SymbolicRibRecord {

  /** Stable-state plane in which the candidate was selected. */
  public enum Plane {
    MAIN,
    BGP,
    ISIS_L1,
    ISIS_L2
  }

  @Nonnull private final Plane _plane;
  @Nonnull private final String _router;
  @Nonnull private final String _vrf;
  @Nonnull private final String _prefix;
  @Nonnull private final String _protocol;
  @Nonnull private final String _nextHop;
  @Nonnull private final String _nextHopIp;
  @Nonnull private final String _nextHopInterface;
  private final long _metric;
  private final int _administrativeCost;
  @Nonnull private final String _route;
  @Nonnull private final String _availabilityGuard;
  @Nonnull private final String _selectionGuard;
  private final boolean _selectionSatisfiable;
  @Nonnull private final ImmutableList<String> _contributionIds;
  @Nonnull private final ImmutableList<String> _routerPath;

  private SymbolicRibRecord(
      Plane plane,
      String router,
      String vrf,
      String prefix,
      String protocol,
      String nextHop,
      String nextHopIp,
      String nextHopInterface,
      long metric,
      int administrativeCost,
      String route,
      String availabilityGuard,
      String selectionGuard,
      boolean selectionSatisfiable,
      Iterable<String> contributionIds,
      Iterable<String> routerPath) {
    _plane = requireNonNull(plane, "plane must be provided");
    _router = requireNonNull(router, "router must be provided");
    _vrf = requireNonNull(vrf, "vrf must be provided");
    _prefix = requireNonNull(prefix, "prefix must be provided");
    _protocol = requireNonNull(protocol, "protocol must be provided");
    _nextHop = requireNonNull(nextHop, "nextHop must be provided");
    _nextHopIp = requireNonNull(nextHopIp, "nextHopIp must be provided");
    _nextHopInterface = requireNonNull(nextHopInterface, "nextHopInterface must be provided");
    _metric = metric;
    _administrativeCost = administrativeCost;
    _route = requireNonNull(route, "route must be provided");
    _availabilityGuard = requireNonNull(availabilityGuard, "availabilityGuard must be provided");
    _selectionGuard = requireNonNull(selectionGuard, "selectionGuard must be provided");
    _selectionSatisfiable = selectionSatisfiable;
    _contributionIds = ImmutableList.copyOf(contributionIds);
    _routerPath = ImmutableList.copyOf(routerPath);
  }

  static <R extends AbstractRouteDecorator> SymbolicRibRecord from(
      Plane plane, GuardedRib<R> rib, GuardedRibEntry<R> entry) {
    return from(plane, rib, entry, true);
  }

  static <R extends AbstractRouteDecorator> SymbolicRibRecord from(
      Plane plane, GuardedRib<R> rib, GuardedRibEntry<R> entry, boolean simplifyGuards) {
    SymbolicRoute<R> symbolic = entry.getSymbolicRoute();
    NextHop nextHop = symbolic.getRoute().getAbstractRoute().getNextHop();
    ImmutableList<String> contributions =
        rib.getContributionIds(symbolic.getKey()).stream()
            .map(
                id ->
                    String.format(
                        "%d:%s:%d:%s:%s",
                        id.getSender().length(),
                        id.getSender(),
                        id.getReceiver().length(),
                        id.getReceiver(),
                        id.getMessageId()))
            .sorted()
            .collect(ImmutableList.toImmutableList());
    return new SymbolicRibRecord(
        plane,
        symbolic.getKey().getRouter(),
        symbolic.getKey().getVrf(),
        symbolic.getKey().getNetwork().toString(),
        symbolic.getKey().getProtocol().toString(),
        nextHop.toString(),
        nextHopIp(nextHop),
        nextHopInterface(nextHop),
        symbolic.getRoute().getAbstractRoute().getMetric(),
        symbolic.getRoute().getAbstractRoute().getAdministrativeCost(),
        symbolic.getRoute().toString(),
        guardText(symbolic.getAvailabilityGuard(), simplifyGuards),
        guardText(entry.getSelectionGuard(), simplifyGuards),
        entry.getSelectionGuard().isSatisfiable(),
        contributions,
        symbolic.getProvenance().getRouterPath());
  }

  private static String guardText(RouteGuard guard, boolean simplifyGuards) {
    return (simplifyGuards ? guard.simplifyForDisplay() : guard).toString();
  }

  private static String nextHopIp(NextHop nextHop) {
    if (nextHop instanceof NextHopIp) {
      return ((NextHopIp) nextHop).getIp().toString();
    }
    if (nextHop instanceof NextHopInterface && ((NextHopInterface) nextHop).getIp() != null) {
      return ((NextHopInterface) nextHop).getIp().toString();
    }
    return "-";
  }

  private static String nextHopInterface(NextHop nextHop) {
    return nextHop instanceof NextHopInterface
        ? ((NextHopInterface) nextHop).getInterfaceName()
        : "-";
  }

  static Comparator<SymbolicRibRecord> ordering() {
    return Comparator.comparing(SymbolicRibRecord::getRouter)
        .thenComparing(SymbolicRibRecord::getVrf)
        .thenComparing(SymbolicRibRecord::getPrefix)
        .thenComparing(record -> record.getPlane().toString())
        .thenComparing(SymbolicRibRecord::getRoute);
  }

  @Nonnull
  public Plane getPlane() {
    return _plane;
  }

  @Nonnull
  public String getRouter() {
    return _router;
  }

  @Nonnull
  public String getVrf() {
    return _vrf;
  }

  @Nonnull
  public String getPrefix() {
    return _prefix;
  }

  @Nonnull
  public String getProtocol() {
    return _protocol;
  }

  @Nonnull
  public String getNextHop() {
    return _nextHop;
  }

  @Nonnull
  public String getNextHopIp() {
    return _nextHopIp;
  }

  @Nonnull
  public String getNextHopInterface() {
    return _nextHopInterface;
  }

  public long getMetric() {
    return _metric;
  }

  public int getAdministrativeCost() {
    return _administrativeCost;
  }

  @Nonnull
  public String getRoute() {
    return _route;
  }

  @Nonnull
  public String getAvailabilityGuard() {
    return _availabilityGuard;
  }

  @Nonnull
  public String getSelectionGuard() {
    return _selectionGuard;
  }

  public boolean getSelectionSatisfiable() {
    return _selectionSatisfiable;
  }

  @Nonnull
  public ImmutableList<String> getContributionIds() {
    return _contributionIds;
  }

  @Nonnull
  public ImmutableList<String> getRouterPath() {
    return _routerPath;
  }
}
