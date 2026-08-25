package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AbstractRouteBuilder;
import org.batfish.datamodel.AbstractRouteDecorator;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.routing_policy.Environment.Direction;
import org.batfish.datamodel.routing_policy.RoutingPolicy;

/** Executes Batfish routing policies without reimplementing policy matching or transformation. */
public final class BatfishRoutingPolicyProcessor {

  private BatfishRoutingPolicyProcessor() {}

  /**
   * Evaluates one route using the exact {@link RoutingPolicy#process} interpreter.
   *
   * <p>The caller supplies the protocol-specific output builder. This is important for
   * redistribution: OSPF, IS-IS, and BGP builders have different mandatory attributes and must be
   * initialized by their Batfish protocol adapters, not by this common symbolic layer.
   */
  @Nonnull
  public static <R extends AbstractRoute> BatfishRoutingPolicyResult<R> process(
      Configuration configuration,
      String policyName,
      AbstractRouteDecorator inputRoute,
      AbstractRouteBuilder<?, R> outputBuilder,
      Direction direction,
      String targetVrf) {
    requireNonNull(configuration, "configuration must be provided");
    requireNonNull(policyName, "policyName must be provided");
    requireNonNull(inputRoute, "inputRoute must be provided");
    requireNonNull(outputBuilder, "outputBuilder must be provided");
    requireNonNull(direction, "direction must be provided");
    requireNonNull(targetVrf, "targetVrf must be provided");
    RoutingPolicy policy = configuration.getRoutingPolicies().get(policyName);
    if (policy == null) {
      return BatfishRoutingPolicyResult.policyNotFound();
    }
    if (!policy.process(inputRoute, outputBuilder, direction)) {
      return BatfishRoutingPolicyResult.denied();
    }
    return BatfishRoutingPolicyResult.accepted(
        new AnnotatedRoute<>(outputBuilder.build(), targetVrf));
  }
}
