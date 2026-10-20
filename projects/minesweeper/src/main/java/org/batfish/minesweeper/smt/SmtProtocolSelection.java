package org.batfish.minesweeper.smt;

import com.google.common.collect.ImmutableSet;
import java.util.Arrays;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Collectors;
import org.batfish.common.BatfishException;

/** Run-level selection of dynamic routing protocols included in an SMT encoding. */
public final class SmtProtocolSelection {

  public static final String ENVIRONMENT_VARIABLE = "SMT_PROTOCOLS";
  public static final String SYSTEM_PROPERTY = "batfish.smt.protocols";

  public enum Family {
    BGP,
    OSPF,
    ISIS
  }

  private static final ImmutableSet<Family> ALL = ImmutableSet.copyOf(Family.values());

  private SmtProtocolSelection() {}

  /** Reads the system property first, then the environment variable, defaulting to all families. */
  public static ImmutableSet<Family> fromRuntime() {
    String value = System.getProperty(SYSTEM_PROPERTY);
    if (value == null || value.trim().isEmpty()) {
      value = System.getenv(ENVIRONMENT_VARIABLE);
    }
    return value == null || value.trim().isEmpty() ? ALL : parse(value);
  }

  /** Parses a comma-separated list such as {@code bgp} or {@code bgp,isis}. */
  public static ImmutableSet<Family> parse(String value) {
    if (value == null || value.trim().isEmpty()) {
      throw new BatfishException("SMT protocol selection must not be empty");
    }
    ImmutableSet.Builder<Family> selected = ImmutableSet.builder();
    for (String token : value.split(",", -1)) {
      String normalized = token.trim().toLowerCase(Locale.ROOT).replace("-", "").replace("_", "");
      switch (normalized) {
        case "bgp":
          selected.add(Family.BGP);
          break;
        case "ospf":
          selected.add(Family.OSPF);
          break;
        case "isis":
          selected.add(Family.ISIS);
          break;
        default:
          throw new BatfishException(
              String.format(
                  "Unsupported SMT protocol '%s'; expected a comma-separated subset of %s",
                  token,
                  Arrays.stream(Family.values())
                      .map(family -> family.name().toLowerCase(Locale.ROOT))
                      .collect(Collectors.joining(","))));
      }
    }
    return selected.build();
  }

  public static String format(Set<Family> families) {
    return families.stream()
        .map(family -> family.name().toLowerCase(Locale.ROOT))
        .sorted()
        .collect(Collectors.joining(","));
  }
}
