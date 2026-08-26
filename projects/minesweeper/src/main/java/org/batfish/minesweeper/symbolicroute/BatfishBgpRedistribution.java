package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.routing_policy.Environment.Direction.OUT;
import static org.batfish.dataplane.protocols.BgpProtocolHelper.convertNonBgpRouteToBgpRoute;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.routing_policy.RoutingPolicy;

/** Batfish-backed conversion of connected/static main-RIB routes into locally originated BGP. */
public final class BatfishBgpRedistribution {

  private BatfishBgpRedistribution() {}

  @Nonnull
  public static BatfishRoutingPolicyResult<Bgpv4Route> redistribute(
      Configuration configuration,
      BgpProcess process,
      String policyName,
      AnnotatedRoute<AbstractRoute> sourceRoute,
      String targetVrf,
      RoutingProtocol targetProtocol) {
    requireNonNull(configuration, "configuration must be provided");
    requireNonNull(process, "process must be provided");
    requireNonNull(policyName, "policyName must be provided");
    requireNonNull(sourceRoute, "sourceRoute must be provided");
    requireNonNull(targetVrf, "targetVrf must be provided");
    if (targetProtocol != RoutingProtocol.BGP && targetProtocol != RoutingProtocol.IBGP) {
      throw new IllegalArgumentException("BGP redistribution target must be BGP or IBGP");
    }
    RoutingPolicy policy = configuration.getRoutingPolicies().get(policyName);
    if (policy == null) {
      return BatfishRoutingPolicyResult.policyNotFound();
    }
    Bgpv4Route.Builder output =
        convertNonBgpRouteToBgpRoute(
            sourceRoute,
            process.getRouterId(),
            sourceRoute.getAbstractRoute().getNextHopIp(),
            process.getAdminCost(targetProtocol),
            targetProtocol)
        .setNonRouting(true);
    if (!policy.processBgpRoute(sourceRoute, output, null, OUT)) {
      return BatfishRoutingPolicyResult.denied();
    }
    return BatfishRoutingPolicyResult.accepted(new AnnotatedRoute<>(output.build(), targetVrf));
  }
}
