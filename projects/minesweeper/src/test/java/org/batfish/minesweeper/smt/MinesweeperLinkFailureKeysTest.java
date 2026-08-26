package org.batfish.minesweeper.smt;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.Interface;
import org.batfish.minesweeper.GraphEdge;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.junit.Test;

public final class MinesweeperLinkFailureKeysTest {

  @Test
  public void testForwardAndReverseEdgesShareCanonicalKey() {
    Configuration r1 = configuration("r1");
    Configuration r4 = configuration("r4");
    Interface r1Interface = Interface.builder().setName("Ethernet14").setOwner(r1).build();
    Interface r4Interface = Interface.builder().setName("Ethernet41").setOwner(r4).build();
    GraphEdge forward = new GraphEdge(r1Interface, r4Interface, "r1", "r4", false, false);
    GraphEdge reverse = new GraphEdge(r4Interface, r1Interface, "r4", "r1", false, false);

    assertThat(
        MinesweeperLinkFailureKeys.fromGraphEdge(forward).get(),
        equalTo(LinkFailureKey.of("r1", "r4")));
    assertThat(
        MinesweeperLinkFailureKeys.fromGraphEdge(reverse),
        equalTo(MinesweeperLinkFailureKeys.fromGraphEdge(forward)));
  }

  private static Configuration configuration(String hostname) {
    return Configuration.builder()
        .setHostname(hostname)
        .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
        .build();
  }
}
