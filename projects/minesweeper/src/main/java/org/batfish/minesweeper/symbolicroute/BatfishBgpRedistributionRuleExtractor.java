package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import static org.batfish.datamodel.RoutingProtocol.BGP;

import com.google.common.collect.ImmutableList;
import java.util.Map;
import java.util.TreeMap;
import javax.annotation.Nonnull;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Vrf;

/** Extracts BGP redistribution boundaries from Batfish's normalized configuration model. */
public final class BatfishBgpRedistributionRuleExtractor {

  private BatfishBgpRedistributionRuleExtractor() {}

  /** Returns one deterministic rule for every VRF whose BGP process has a redistribution policy. */
  @Nonnull
  public static ImmutableList<BatfishBgpRedistributionRule> extract(
      Map<String, Configuration> configurations) {
    requireNonNull(configurations, "configurations must be provided");
    ImmutableList.Builder<BatfishBgpRedistributionRule> rules = ImmutableList.builder();
    for (Map.Entry<String, Configuration> nodeEntry :
        new TreeMap<>(configurations).entrySet()) {
      Configuration configuration = nodeEntry.getValue();
      if (!nodeEntry.getKey().equals(configuration.getHostname())) {
        throw new IllegalArgumentException("configuration key must equal hostname");
      }
      for (Map.Entry<String, Vrf> vrfEntry :
          new TreeMap<>(configuration.getVrfs()).entrySet()) {
        String vrfName = vrfEntry.getKey();
        BgpProcess process = vrfEntry.getValue().getBgpProcess();
        if (process == null || process.getRedistributionPolicy() == null) {
          continue;
        }
        String policyName = process.getRedistributionPolicy();
        if (!configuration.getRoutingPolicies().containsKey(policyName)) {
          throw new IllegalArgumentException(
              String.format(
                  "BGP redistribution policy %s is missing on %s VRF %s",
                  policyName, configuration.getHostname(), vrfName));
        }
        rules.add(
            new BatfishBgpRedistributionRule(
                ruleId(configuration.getHostname(), vrfName, policyName),
                configuration.getHostname(),
                vrfName,
                vrfName,
                policyName,
                BGP));
      }
    }
    return rules.build();
  }

  private static String ruleId(String hostname, String vrf, String policy) {
    return String.format(
        "bgp-redist:%d:%s:%d:%s:%d:%s",
        hostname.length(), hostname, vrf.length(), vrf, policy.length(), policy);
  }
}
