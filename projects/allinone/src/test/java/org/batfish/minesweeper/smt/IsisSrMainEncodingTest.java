package org.batfish.minesweeper.smt;

import static org.batfish.minesweeper.smt.Encoder.OUTPUT_DIRECTORY_PROPERTY;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.greaterThan;
import static org.hamcrest.Matchers.instanceOf;

import com.google.devtools.build.runfiles.Runfiles;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Set;
import org.batfish.common.Answerer;
import org.batfish.datamodel.IpWildcard;
import org.batfish.datamodel.answers.AnswerElement;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.answers.SmtReachabilityAnswerElement;
import org.batfish.minesweeper.question.SmtReachabilityQuestionPlugin.ReachabilityQuestion;
import org.batfish.minesweeper.utils.ConfigLoader;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;

/** End-to-end regression test for IS-IS SPF and SR policy equations in the main SMT encoding. */
public final class IsisSrMainEncodingTest {

  @Rule public TemporaryFolder _temp = new TemporaryFolder();

  @Test
  public void testIsisAndSrArePartOfMainEncoding() throws Exception {
    Runfiles runfiles = Runfiles.create();
    String network = runfiles.rlocation("batfish/networks/tolerance_sr_te_demo_1_d_x");
    TestrigText testrig =
        TestrigText.builder()
            .setConfigurationBytes(
                ConfigLoader.loadAllFiles(Paths.get(network, "configs").toString(), ".cfg"))
            .build();
    Batfish batfish = BatfishTestUtils.getBatfishFromTestrigText(testrig, _temp);
    batfish.computeDataPlane(batfish.getSnapshot());

    Path output = _temp.newFolder("main-encoding").toPath();
    System.setProperty(OUTPUT_DIRECTORY_PROPERTY, output.toString());
    try {
      ReachabilityQuestion question = new ReachabilityQuestion();
      question.setIngressNodeRegex("s");
      question.setFinalNodeRegex("d");
      question.setDstIps(Set.of(IpWildcard.parse("5.5.5.5/32")));
      AnswerElement answer = Answerer.create(question, batfish).answer(batfish.getSnapshot());
      assertThat(answer, instanceOf(SmtReachabilityAnswerElement.class));
    } finally {
      System.clearProperty(OUTPUT_DIRECTORY_PROPERTY);
    }

    String smt =
        new String(Files.readAllBytes(output.resolve("smt_encoding.smt2")), StandardCharsets.UTF_8);
    assertThat(smt, containsString("Config_s_Interface_GigabitEthernet0_0_Isis_L2_cost"));
    assertThat(smt, containsString("ISIS-SPF_ISIS_L2_s_5_5_5_5_32_distance"));
    assertThat(smt, containsString("ISIS-SPF_ISIS_L2_s_5_5_5_5_32_ecmp_"));
    assertThat(
        smt, containsString("Config_s_SrPolicy_split_to_D_Path_explicit_upper_via_A_weight"));
    assertThat(smt, containsString("SR-POLICY_s_split_to_D_explicit_upper_via_A_available"));
    assertThat(smt, containsString("SR-POLICY_s_split_to_D_explicit_upper_via_A_selected"));
    assertThat(
        smt, containsString("SR-POLICY_s_split_to_D_explicit_upper_via_A_segment_0_forward_"));
    // Declaration + selection equation + use in the main CONTROL-FORWARDING equation.
    assertThat(
        occurrences(smt, "SR-POLICY_s_split_to_D_explicit_upper_via_A_selected"), greaterThan(2));
  }

  private static int occurrences(String text, String value) {
    int count = 0;
    for (int offset = 0; (offset = text.indexOf(value, offset)) >= 0; offset += value.length()) {
      count++;
    }
    return count;
  }
}
