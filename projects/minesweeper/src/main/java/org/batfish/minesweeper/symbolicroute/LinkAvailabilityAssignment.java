package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableMap;
import java.util.Map;
import javax.annotation.Nonnull;

/** Concrete link state using the Step-2 polarity {@code true=up}, {@code false=failed}. */
public final class LinkAvailabilityAssignment {

  @Nonnull private final ImmutableMap<LinkFailureKey, Boolean> _isUp;

  public LinkAvailabilityAssignment(Map<LinkFailureKey, Boolean> isUp) {
    _isUp = ImmutableMap.copyOf(requireNonNull(isUp, "link states must be provided"));
  }

  public boolean isUp(LinkFailureKey key) {
    Boolean value = _isUp.get(requireNonNull(key, "link key must be provided"));
    if (value == null) {
      throw new IllegalArgumentException("link assignment is missing a canonical key");
    }
    return value;
  }

  /** Counts down components, never up components. */
  public int failureCount() {
    return (int) _isUp.values().stream().filter(isUp -> !isUp).count();
  }

  public boolean isWithinFailureBudget(int maximumFailures) {
    if (maximumFailures < 0) {
      throw new IllegalArgumentException("failure budget must be nonnegative");
    }
    return failureCount() <= maximumFailures;
  }
}
