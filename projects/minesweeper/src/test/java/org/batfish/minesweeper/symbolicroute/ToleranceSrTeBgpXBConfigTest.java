package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.instanceOf;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.DataPlane;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.route.nh.NextHopIp;
import org.batfish.main.Batfish;
import org.batfish.main.BatfishTestUtils;
import org.batfish.main.TestrigText;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.TemporaryFolder;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Acceptance test for the SR-TE demo extended with X-B and BGP local preference. */
@RunWith(JUnit4.class)
public final class ToleranceSrTeBgpXBConfigTest {
  private static final String SNAPSHOT = "networks/tolerance_sr_te_demo_bgp_x_b/configs/";

  @Rule public TemporaryFolder _folder = new TemporaryFolder();

  @Test
  public void testAllLinksUpXUsesPreferredDirectBgpRoute() throws IOException {
    SortedMap<String, byte[]> configurationBytes = new TreeMap<>();
    for (String filename : ImmutableList.of("A.cfg", "B.cfg", "D.cfg", "S.cfg", "X.cfg")) {
      configurationBytes.put(filename, Files.readAllBytes(Paths.get(SNAPSHOT + filename)));
    }
    Batfish batfish =
        BatfishTestUtils.getBatfishFromTestrigText(
            TestrigText.builder().setConfigurationBytes(configurationBytes).build(), _folder);
    SortedMap<String, Configuration> configurations =
        batfish.loadConfigurations(batfish.getSnapshot());

    assertThat(configurations.keySet().toString(), equalTo("[a, b, d, s, x]"));
    assertThat(configurations.get("x").getAllInterfaces().keySet(), hasSize(3));
    assertThat(configurations.get("b").getAllInterfaces().keySet(), hasSize(3));

    batfish.computeDataPlane(batfish.getSnapshot());
    DataPlane dataPlane = batfish.loadDataPlane(batfish.getSnapshot());
    Set<AnnotatedRoute<AbstractRoute>> xRoutesToD =
        dataPlane
            .getRibs()
            .get("x")
            .get(Configuration.DEFAULT_VRF_NAME)
            .longestPrefixMatch(Ip.parse("5.5.5.5"));

    assertThat(xRoutesToD, hasSize(1));
    AbstractRoute selected = xRoutesToD.iterator().next().getRoute();
    assertThat(selected, instanceOf(Bgpv4Route.class));
    assertThat(((Bgpv4Route) selected).getLocalPreference(), equalTo(200L));
    assertThat(selected.getNextHop(), equalTo(NextHopIp.of(Ip.parse("10.0.15.2"))));
  }
}
