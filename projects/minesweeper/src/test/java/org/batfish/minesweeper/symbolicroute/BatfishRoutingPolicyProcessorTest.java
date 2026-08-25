package org.batfish.minesweeper.symbolicroute;

import static org.batfish.datamodel.ConfigurationFormat.CISCO_IOS;
import static org.batfish.datamodel.routing_policy.Environment.Direction.OUT;
import static org.batfish.datamodel.routing_policy.statement.Statements.ExitAccept;
import static org.batfish.datamodel.routing_policy.statement.Statements.ExitReject;
import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.StaticRoute;
import org.batfish.datamodel.routing_policy.RoutingPolicy;
import org.batfish.datamodel.routing_policy.expr.LiteralLong;
import org.batfish.datamodel.routing_policy.statement.SetMetric;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests exact delegation to Batfish's concrete routing-policy interpreter. */
@RunWith(JUnit4.class)
public final class BatfishRoutingPolicyProcessorTest {

  private Configuration _configuration;
  private AnnotatedRoute<StaticRoute> _input;

  @Before
  public void setup() {
    _configuration =
        new NetworkFactory()
            .configurationBuilder()
            .setHostname("r1")
            .setConfigurationFormat(CISCO_IOS)
            .build();
    _input =
        new AnnotatedRoute<>(
            StaticRoute.testBuilder()
                .setNetwork(Prefix.parse("192.0.2.0/24"))
                .setMetric(10L)
                .build(),
            "source");
  }

  @Test
  public void testAcceptedTransformationExactlyMatchesDirectBatfishExecution() {
    RoutingPolicy policy =
        RoutingPolicy.builder()
            .setOwner(_configuration)
            .setName("transform")
            .addStatement(new SetMetric(new LiteralLong(50L)))
            .addStatement(ExitAccept.toStaticStatement())
            .build();
    StaticRoute.Builder directBuilder = _input.getRoute().toBuilder();
    assertThat(policy.process(_input, directBuilder, OUT), equalTo(true));
    StaticRoute direct = directBuilder.build();

    BatfishRoutingPolicyResult<StaticRoute> result =
        BatfishRoutingPolicyProcessor.process(
            _configuration, "transform", _input, _input.getRoute().toBuilder(), OUT, "target");

    assertThat(result.getOutcome(), equalTo(BatfishRoutingPolicyResult.Outcome.ACCEPTED));
    assertThat(result.getOutputRoute().get().getRoute(), equalTo(direct));
    assertThat(result.getOutputRoute().get().getSourceVrf(), equalTo("target"));
  }

  @Test
  public void testDeniedPolicyProducesNoRoute() {
    RoutingPolicy.builder()
        .setOwner(_configuration)
        .setName("deny")
        .addStatement(ExitReject.toStaticStatement())
        .build();

    BatfishRoutingPolicyResult<StaticRoute> result =
        BatfishRoutingPolicyProcessor.process(
            _configuration, "deny", _input, _input.getRoute().toBuilder(), OUT, "target");

    assertThat(result.getOutcome(), equalTo(BatfishRoutingPolicyResult.Outcome.DENIED));
    assertThat(result.getOutputRoute().isPresent(), equalTo(false));
  }

  @Test
  public void testMissingPolicyIsDistinctFromPolicyDeny() {
    BatfishRoutingPolicyResult<StaticRoute> result =
        BatfishRoutingPolicyProcessor.process(
            _configuration, "missing", _input, _input.getRoute().toBuilder(), OUT, "target");

    assertThat(result.getOutcome(), equalTo(BatfishRoutingPolicyResult.Outcome.POLICY_NOT_FOUND));
    assertThat(result.getOutputRoute().isPresent(), equalTo(false));
  }
}
