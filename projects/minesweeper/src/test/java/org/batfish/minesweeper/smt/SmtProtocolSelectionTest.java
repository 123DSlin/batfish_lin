package org.batfish.minesweeper.smt;

import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.containsInAnyOrder;
import static org.hamcrest.Matchers.equalTo;

import org.batfish.common.BatfishException;
import org.junit.Rule;
import org.junit.Test;
import org.junit.rules.ExpectedException;

public final class SmtProtocolSelectionTest {

  @Rule public ExpectedException _exception = ExpectedException.none();

  @Test
  public void testSingleProtocol() {
    assertThat(
        SmtProtocolSelection.parse("bgp"), containsInAnyOrder(SmtProtocolSelection.Family.BGP));
  }

  @Test
  public void testMultipleProtocolsAndAliases() {
    assertThat(
        SmtProtocolSelection.parse("BGP, IS-IS, ospf"),
        containsInAnyOrder(
            SmtProtocolSelection.Family.BGP,
            SmtProtocolSelection.Family.ISIS,
            SmtProtocolSelection.Family.OSPF));
  }

  @Test
  public void testStableOutputFormat() {
    assertThat(
        SmtProtocolSelection.format(SmtProtocolSelection.parse("isis,bgp")), equalTo("bgp,isis"));
  }

  @Test
  public void testUnsupportedProtocolRejected() {
    _exception.expect(BatfishException.class);
    _exception.expectMessage("Unsupported SMT protocol");

    SmtProtocolSelection.parse("rip");
  }
}
