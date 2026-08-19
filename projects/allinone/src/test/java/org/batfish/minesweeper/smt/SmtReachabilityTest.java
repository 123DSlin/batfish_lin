package org.batfish.minesweeper.smt;

import org.batfish.common.Answerer;
// import org.batfish.common.NetworkSnapshot;
import org.batfish.datamodel.IpWildcard;
import org.batfish.datamodel.Zone;
import org.batfish.datamodel.answers.AnswerElement;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.batfish.minesweeper.answers.SmtOneAnswerElement;
import org.batfish.question.routes.RoutesQuestion;
import org.batfish.question.routes.RoutesAnswerer;
import org.batfish.minesweeper.answers.SmtReachabilityAnswerElement;
import org.batfish.minesweeper.question.SmtReachabilityQuestionPlugin.ReachabilityQuestion;
import org.batfish.minesweeper.question.SmtBoundedLengthQuestionPlugin.BoundedLengthQuestion;
import org.batfish.minesweeper.question.SmtBlackholeQuestionPlugin.BlackholeQuestion;
import org.batfish.minesweeper.utils.ConfigLoader;
import org.batfish.minesweeper.utils.RibPrinter;
import static org.batfish.minesweeper.smt.Encoder.createOutputDirectory;

import static org.hamcrest.Matchers.instanceOf;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.is;

import org.junit.rules.TemporaryFolder;
import org.junit.Before;
import org.junit.Rule;
import org.junit.Test;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.io.IOException;
import java.time.ZoneId;
import java.util.Set;
import java.util.SortedMap;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

import com.google.devtools.build.runfiles.Runfiles;

public class SmtReachabilityTest {
    @Rule public TemporaryFolder _temp = new TemporaryFolder();

    private Batfish _batfish;
    // private NetworkSnapshot _snapshot;

    // printers for output files
    private PrintWriter _bgpRouteWriter;
    private PrintWriter _dataPlaneWriter;

    @Before
    public void setup() throws IOException {
        System.out.println();
        // Beijing timezone
        ZoneId chinaZone = ZoneId.of("Asia/Shanghai");
        // Current time in Beijing
        LocalDateTime beijingTime = LocalDateTime.now(chinaZone);
        // Format output
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
        String formattedNow = beijingTime.format(formatter);
        // Output the beijing time for the beginning of the test running
        System.out.println("=== Running test at " + formattedNow + " (Beijing Time) ===");

        // create a smt output directory
        String outputDir = createOutputDirectory();
        String outputBgpRouteFileName = outputDir + "/0_ebgp_routes.txt";
        String outputDataPlaneFileName = outputDir + "/0_data_plane.txt";
        File outputBgpRouteFile = new File(outputBgpRouteFileName);
        File outputDataPlaneFile = new File(outputDataPlaneFileName);
        try {
            _bgpRouteWriter = new PrintWriter(new FileWriter(outputBgpRouteFile, true));
            _dataPlaneWriter = new PrintWriter(new FileWriter(outputDataPlaneFile, true));
        } catch (IOException e) {
            System.err.println("Error: Unable to create file: " + e.getMessage());
        }

        // read the configurations from the filesystem
        Runfiles runfiles = Runfiles.create();

        // String configPath = runfiles.rlocation("batfish/networks/userstudy_networks/userstudy_network");
        // String configPath = runfiles.rlocation("batfish/networks/userstudy_networks/userstudy_network_hard");
         String configPath = runfiles.rlocation("batfish/networks/userstudy_networks/userstudy_network_accessment");
        // String configPath = runfiles.rlocation("batfish/networks/userstudy_networks/userstudy_network_accessment_intro");
        // String configPath = runfiles.rlocation("batfish/networks/userstudy_networks/userstudy_network_coursera");

        // -------------------------------------------------------------

        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree4pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree8pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree12pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree16pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree20pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree24pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree28pol");
        // String configPath = runfiles.rlocation("batfish/benchmarks/FatTrees/fattree32pol");

        // -------------------------------------------------------------

        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line10");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line100");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line1000");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line2000");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line5000");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Lines/line10000");

        // -------------------------------------------------------------

        // String configPath = runfiles.rlocation("batfish/benchmarks/Bics/bgp");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Columbus/bgp");
        // String configPath = runfiles.rlocation("batfish/benchmarks/USCarrier/bgp");
        // String configPath = runfiles.rlocation("batfish/benchmarks/Internet2/");

        // -------------------------------------------------------------

        TestrigText _testrig = loadConfigurations(configPath);
        _batfish = BatfishTestUtils.getBatfishFromTestrigText(_testrig, _temp);

        long start = System.currentTimeMillis();
        // compute data plane for printing RIBs before
        _batfish.computeDataPlane(_batfish.getSnapshot(), _bgpRouteWriter);
        // print MAIN RIB (forwarding table) of the data plane: one best route per prefix per node.
        RoutesQuestion routesQuestion = new RoutesQuestion();
        RoutesAnswerer routesAnswerer = new RoutesAnswerer(routesQuestion, _batfish);
        AnswerElement routesAnswer = routesAnswerer.answer(_batfish.getSnapshot());
        RibPrinter.printRouteTable(routesAnswer, _dataPlaneWriter);
        long end = System.currentTimeMillis();
        System.out.println("[Time taken to compute data plane and print RIBs: " + (end - start) + " ms]");
    }

    /**
     * Test network property: Reachability (or Isolation with negated) via SMT.
     * You can set node failures (or not) or edge failures (or not).
     */
    @Test
    public void testReachability() {
        final ReachabilityQuestion question = new ReachabilityQuestion();

        // user-study specification 1: ECMP reachability
        // question.setIngressNodeRegex("r3");
        // question.setFinalNodeRegex("isp2");
        // IpWildcard ipWildcard = IpWildcard.parse("203.0.113.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // user-study specification 2: Private prefix filtering
        // question.setIngressNodeRegex("r3");
        // question.setFinalNodeRegex("customer");
        // IpWildcard ipWildcard = IpWildcard.parse("192.168.128.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);
        //
        // question.setIngressNodeRegex("r3");
        // question.setFinalNodeRegex("customer");
        // IpWildcard ipWildcard = IpWildcard.parse("192.168.129.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);

        // user-study specification 3: Customer reachability
        question.setIngressNodeRegex("customer");
        question.setFinalNodeRegex("isp1");
        IpWildcard ipWildcard = IpWildcard.parse("198.51.100.0/24");
        question.setDstIps(Set.of(ipWildcard));

        // user-study specification 4: No transit
        // question.setIngressNodeRegex("isp2");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("192.0.2.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);
        //
        // question.setIngressNodeRegex("isp2");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("198.51.100.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);
        //
        // question.setIngressNodeRegex("isp1");
        // question.setFinalNodeRegex("isp2");
        // IpWildcard ipWildcard = IpWildcard.parse("203.0.113.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);

        // -------------------------------------------------------------

        // Specification 01: Qualification test 1
        // question.setIngressNodeRegex("customer");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("192.0.2.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Specification 02: Qualification test 2
        // question.setIngressNodeRegex("customer");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("198.51.100.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);

        // -------------------------------------------------------------

        // Specification 01: Qualification test 1 (for introduction)
        // question.setIngressNodeRegex("customer");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.0.0.0/8");
        // question.setDstIps(Set.of(ipWildcard));

        // Specification 02: Qualification test 2 (for introduction)
        // question.setIngressNodeRegex("customer");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("192.168.0.0/16");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);

        // -------------------------------------------------------------

        // Specification 01: Coursera test 1
        // question.setIngressNodeRegex("r1");
        // question.setFinalNodeRegex("customer");
        // IpWildcard ipWildcard = IpWildcard.parse("192.168.0.0/16");
        // question.setDstIps(Set.of(ipWildcard));
        // question.setNegate(true);

        // -------------------------------------------------------------

        // FatTree benchmarks - fattree4pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-19");
        // IpWildcard ipWildcard = IpWildcard.parse("70.0.19.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree8pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-79");
        // IpWildcard ipWildcard = IpWildcard.parse("70.0.79.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree12pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-179");
        // IpWildcard ipWildcard = IpWildcard.parse("70.0.179.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree16pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-319");
        // IpWildcard ipWildcard = IpWildcard.parse("70.1.63.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree20pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-499");
        // IpWildcard ipWildcard = IpWildcard.parse("70.1.243.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree24pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-719");
        // IpWildcard ipWildcard = IpWildcard.parse("70.2.207.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree28pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-979");
        // IpWildcard ipWildcard = IpWildcard.parse("70.3.211.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // FatTree benchmarks - fattree32pol
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("edge-1279");
        // IpWildcard ipWildcard = IpWildcard.parse("70.4.255.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // -------------------------------------------------------------

        // Line benchmarks - line10
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.1.1.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Line benchmarks - line100
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.5.4.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Line benchmarks - line1000
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.5.49.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Line benchmarks - line2000
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.10.49.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Line benchmarks - line5000
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.20.62.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // Line benchmarks - line10000
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("isp1");
        // IpWildcard ipWildcard = IpWildcard.parse("10.20.124.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // -------------------------------------------------------------

        // Bics benchmarks
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peergeneva_8");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.8.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerbrussels_4");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.4.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerfrankfurt_7");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.27.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("luxembourg");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.51.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("madrid");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.56.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("strasbourg");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.64.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("zagreb");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.59.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("warsaw");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.67.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peergeneva_9");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.54.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peermarseille_13");
        // IpWildcard ipWildcard = IpWildcard.parse("200.1.19.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // -------------------------------------------------------------

        // Columbus benchmarks
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("grenada");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.55.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerdominicanttrepublic_1");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.1.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peernodeid1_2");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.4.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peernodeid31_6");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.6.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("nodeid44");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.100.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("nodeid50");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.101.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerstttcroix_13");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.102.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peernodeid46_10");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.22.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerpanama_12");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.35.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("curacao");
        // IpWildcard ipWildcard = IpWildcard.parse("200.2.37.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // -------------------------------------------------------------

        // USCarrier benchmarks
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peerjacksonvilleid5_8");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.8.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("peeralbany_0");
        // IpWildcard ipWildcard = IpWildcard.parse("128.0.0.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("cartersville");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.127.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("kinston");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.145.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("warwick");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.169.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("waynesboro");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.172.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("greenwood");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.178.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("hagerstown");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.197.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("aiken");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.202.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex(".*");
        // question.setFinalNodeRegex("ringgold");
        // IpWildcard ipWildcard = IpWildcard.parse("200.4.214.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        // -------------------------------------------------------------

        // Internet2 benchmarks
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("100.64.10.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("205.213.200.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("128.10.50.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("128.2.100.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("128.206.50.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("128.101.10.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("63.193.200.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("198.48.92.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("74.115.8.0/24");
        // question.setDstIps(Set.of(ipWildcard));
        //
        // question.setIngressNodeRegex("chic-re1");
        // question.setFinalNodeRegex("wiscr");
        // IpWildcard ipWildcard = IpWildcard.parse("63.164.11.0/24");
        // question.setDstIps(Set.of(ipWildcard));

        final AnswerElement answer = Answerer.create(question, _batfish).answer(_batfish.getSnapshot());
        assertThat(answer, instanceOf(SmtReachabilityAnswerElement.class));

        final SmtReachabilityAnswerElement smtAnswer = (SmtReachabilityAnswerElement) answer;
        assertThat(smtAnswer.getResult().isVerified(), is(true));
    }

    /**
     * Test network property: Bounded Length via SMT.
     * You can set node failures (or not) or edge failures (or not).
     */
    /*
    @Test
    public void testBoundedLength() {
        final BoundedLengthQuestion question = new BoundedLengthQuestion();
        question.setBound(3);
        question.setIngressNodeRegex("customer1");
        question.setFinalNodeRegex("isp1");
        question.setFinalIfaceRegex("GigabitEthernet3/0");

        final AnswerElement answer = Answerer.create(question, _batfish).answer(_batfish.getSnapshot());
        assertThat(answer, instanceOf(SmtOneAnswerElement.class));

        final SmtOneAnswerElement smtAnswer = (SmtOneAnswerElement) answer;
        assertThat(smtAnswer.getResult().isVerified(), is(true));
    }
     */

    /**
     * Test network property: Bounded Length via SMT.
     * You can set node failures (or not) or edge failures (or not).
     */
    /*
    @Test
    public void testBlackhole() {
        final BlackholeQuestion question = new BlackholeQuestion();
        // question.setIngressNodeRegex("customer1");
        // question.setFinalNodeRegex("isp1");
        // question.setFinalIfaceRegex("GigabitEthernet3/0");

        final AnswerElement answer = Answerer.create(question, _batfish).answer(_batfish.getSnapshot());
        assertThat(answer, instanceOf(SmtOneAnswerElement.class));

        final SmtOneAnswerElement smtAnswer = (SmtOneAnswerElement) answer;
        assertThat(smtAnswer.getResult().isVerified(), is(true));
    }
     */

    /**
     * Load configurations, hosts and iptables files from specified directory.
     *
     * @param configPathStr base path to the directory containing "configs", "hosts", and "iptables" subdirectories.
     * @return TestrigText object containing all loaded file bytes.
     */
    public static TestrigText loadConfigurations(String configPathStr) {
        try {
            // Ensure directory path ends with separator
            if (!configPathStr.endsWith("/") && !configPathStr.endsWith("\\")) {
                configPathStr += System.getProperty("file.separator");
            }

            SortedMap<String, byte[]> configurationsBytes =
                ConfigLoader.loadAllFiles(configPathStr + "configs", ".cfg");
            SortedMap<String, byte[]> hostsBytes =
                ConfigLoader.loadAllFiles(configPathStr + "hosts", ".json");
            SortedMap<String, byte[]> iptablesBytes =
                ConfigLoader.loadAllFiles(configPathStr + "iptables", ".iptables");

            return TestrigText.builder()
                .setConfigurationBytes(configurationsBytes)
                .setHostsBytes(hostsBytes)
                .setIptablesBytes(iptablesBytes)
                .build();

        } catch (IOException e) {
            System.err.println("Failed to load configurations from " + configPathStr + ": " + e.getMessage());
            return TestrigText.builder().build();
        }
    }
}
