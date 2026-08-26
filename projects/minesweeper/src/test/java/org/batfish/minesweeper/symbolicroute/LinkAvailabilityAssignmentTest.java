package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableMap;
import org.junit.Test;

public final class LinkAvailabilityAssignmentTest {

  @Test
  public void testFalseMeansFailureAndBudgetCountsDownLinks() {
    LinkFailureKey r1R2 = LinkFailureKey.of("r1", "r2");
    LinkFailureKey r1R4 = LinkFailureKey.of("r1", "r4");
    LinkAvailabilityAssignment assignment =
        new LinkAvailabilityAssignment(ImmutableMap.of(r1R2, true, r1R4, false));

    assertThat(assignment.isUp(r1R2), equalTo(true));
    assertThat(assignment.isUp(r1R4), equalTo(false));
    assertThat(assignment.failureCount(), equalTo(1));
    assertThat(assignment.isWithinFailureBudget(0), equalTo(false));
    assertThat(assignment.isWithinFailureBudget(1), equalTo(true));
  }
}
