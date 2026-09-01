package org.batfish.minesweeper.symbolicroute;

import static org.batfish.common.topology.TopologyUtil.synthesizeL3Topology;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.microsoft.z3.Context;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.isis.IsisTopology;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.symbolicsr.GuardedSrPolicyContribution;
import org.batfish.minesweeper.symbolicsr.SymbolicSrPolicyRecord;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Parser-driven Stage 7.8 acceptance for guarded SR-policy resolution and reporting. */
@RunWith(JUnit4.class)
public final class ParsedSrPolicyPipelineTest {
  private static final String SNAPSHOT = "networks/sr-symbolic-route/configs/";
  private static final Context CONTEXT = new Context();
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(CONTEXT);

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testParsedIsisAndSrPolicyProduceGuardedForwardingBranch() throws IOException {
    SortedMap<String, byte[]> configurationBytes = new TreeMap<>();
    for (String filename : ImmutableList.of("R1.cfg", "R2.cfg")) {
      configurationBytes.put(filename, Files.readAllBytes(Paths.get(SNAPSHOT + filename)));
    }
    Batfish batfish =
        BatfishTestUtils.getBatfishFromTestrigText(
            TestrigText.builder().setConfigurationBytes(configurationBytes).build(), _folder);
    SortedMap<String, Configuration> configurations =
        batfish.loadConfigurations(batfish.getSnapshot());

    assertThat(configurations.keySet().toString(), equalTo("[r1, r2]"));
    assertThat(
        configurations
            .get("r1")
            .getAllInterfaces()
            .get("GigabitEthernet0/0")
            .getIsis()
            .getPointToPoint(),
        equalTo(true));
    assertThat(
        configurations
            .get("r1")
            .getSegmentRoutingConfig()
            .getVrfs()
            .get(Configuration.DEFAULT_VRF_NAME)
            .getPolicies(),
        hasSize(1));

    batfish.computeDataPlane(batfish.getSnapshot());
    DataPlane dataPlane = batfish.loadDataPlane(batfish.getSnapshot());
    IsisTopology isisTopology =
        IsisTopology.initIsisTopology(configurations, synthesizeL3Topology(configurations));
    BatfishSymbolicRoutePipelineInput input =
        BatfishParsedSnapshotPipelineInputBuilder.build(
            configurations,
            dataPlane.getRibs(),
            batfish.getTopologyProvider().getBgpTopology(batfish.getSnapshot()).getGraph(),
            isisTopology,
            GUARDS,
            ImmutableList.of());

    BatfishSymbolicRoutePipelineResult result = BatfishSymbolicRoutePipeline.run(input);

    assertThat(result.getGuardedSrPolicyDatabase().getCandidates(), hasSize(1));
    assertThat(result.getGuardedSrPolicyDatabase().getContributions(), hasSize(1));
    GuardedSrPolicyContribution contribution =
        result.getGuardedSrPolicyDatabase().getContributions().get(0);
    RouteGuard expected = GUARDS.variable("r1_r2");
    assertThat(contribution.getAvailabilityGuard().isEquivalentTo(expected), equalTo(true));
    assertThat(contribution.getSelectionGuard().isEquivalentTo(expected), equalTo(true));
    assertThat(contribution.getBranch().getTopFirstLabels().get(0).getMplsLabel(), equalTo(16002L));
    assertThat(contribution.getKey().getLinkDependencies(), hasSize(1));
    assertThat(
        contribution.getKey().getLinkDependencies().get(0), equalTo(LinkFailureKey.of("r1", "r2")));

    assertThat(result.getAllSrPolicyRecords(), hasSize(2));
    SymbolicSrPolicyRecord branch =
        result.getAllSrPolicyRecords().stream()
            .filter(record -> record.getKind() == SymbolicSrPolicyRecord.Kind.FORWARDING_BRANCH)
            .findFirst()
            .get();
    assertThat(branch.getLabels(), equalTo(ImmutableList.of(16002L)));
    assertThat(branch.getNextHops(), equalTo(ImmutableList.of("r2/default/GigabitEthernet0/0")));
    assertThat(branch.getLinkDependencies(), equalTo(ImmutableList.of("r1_r2")));
    assertThat(
        result.toSrPolicyJson().contains("\"candidate\" : \"explicit:to-r2\""), equalTo(true));
    assertThat(
        result.toRawSrPolicyJson().contains("\"candidate\" : \"explicit:to-r2\""), equalTo(true));
    assertThat(
        result.toReadableText().contains("SR POLICY FORWARDING BRANCHES"),
        equalTo(true));
    assertThat(result.toReadableText().contains("primary-to-r2"), equalTo(true));
    assertThat(result.toReadableText().contains("FORWARDING_BRANCH"), equalTo(false));
    assertThat(
        result.toRawReadableText().contains("SR POLICY CANDIDATES AND FORWARDING BRANCHES"),
        equalTo(true));
    assertThat(result.toRawReadableText().contains("CANDIDATE"), equalTo(true));
    assertThat(result.toRawReadableText().contains("FORWARDING_BRANCH"), equalTo(true));
  }
}
