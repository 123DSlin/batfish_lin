package org.batfish.minesweeper.smt;

import static org.batfish.minesweeper.smt.Encoder.OUTPUT_DIRECTORY_PROPERTY;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.not;

import com.google.devtools.build.runfiles.Runfiles;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Set;
import org.batfish.common.Answerer;
import org.batfish.datamodel.IpWildcard;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.question.SmtReachabilityQuestionPlugin.ReachabilityQuestion;
import org.batfish.minesweeper.utils.ConfigLoader;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

/** End-to-end checks for run-level protocol filtering of the emitted SMT artifacts. */
public final class SmtProtocolSelectionEncodingTest {

  @Rule public TemporaryFolder _temp = new TemporaryFolder();

  @Test
  public void testBgpOnlyOmitsIsisFromEncodingAndOutputMetadata() throws Exception {
    Runfiles runfiles = Runfiles.create();
    String network = runfiles.rlocation("batfish/networks/tolerance_sr_te_demo_1_d_x");
    TestrigText testrig =
        TestrigText.builder()
            .setConfigurationBytes(
                ConfigLoader.loadAllFiles(Paths.get(network, "configs").toString(), ".cfg"))
            .build();
    Batfish batfish = BatfishTestUtils.getBatfishFromTestrigText(testrig, _temp);
    batfish.computeDataPlane(batfish.getSnapshot());

    Path output = _temp.newFolder("bgp-only-encoding").toPath();
    System.setProperty(OUTPUT_DIRECTORY_PROPERTY, output.toString());
    System.setProperty(SmtProtocolSelection.SYSTEM_PROPERTY, "bgp");
    try {
      ReachabilityQuestion question = new ReachabilityQuestion();
      question.setIngressNodeRegex("s");
      question.setFinalNodeRegex("d");
      question.setDstIps(Set.of(IpWildcard.parse("5.5.5.5/32")));
      Answerer.create(question, batfish).answer(batfish.getSnapshot());
    } finally {
      System.clearProperty(SmtProtocolSelection.SYSTEM_PROPERTY);
      System.clearProperty(OUTPUT_DIRECTORY_PROPERTY);
    }

    String smt =
        new String(Files.readAllBytes(output.resolve("smt_encoding.smt2")), StandardCharsets.UTF_8);
    assertThat(smt, not(containsString("ISIS-SPF_")));
    assertThat(smt, not(containsString("_Isis_")));
    assertThat(smt, not(containsString("SR-POLICY_")));
    assertThat(
        new String(Files.readAllBytes(output.resolve("0_protocols.txt")), StandardCharsets.UTF_8)
            .trim(),
        equalTo("bgp"));
  }
}
