package org.batfish.minesweeper.smt;

import static com.google.common.base.MoreObjects.firstNonNull;
import static org.batfish.datamodel.isis.IsisInterfaceMode.ACTIVE;

import com.microsoft.z3.ArithExpr;
import com.microsoft.z3.Context;
import com.microsoft.z3.Expr;
import com.microsoft.z3.Solver;
import java.util.Map;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.IsisRoute;
import org.batfish.datamodel.isis.IsisInterfaceLevelSettings;
import org.batfish.datamodel.isis.IsisLevel;

/** Dedicated Minesweeper SMT support for link-state IS-IS SPF semantics. */
public final class IsisSpfSmtEncoder {

  public static final long MAX_WIDE_METRIC = 0xFFFFFFL;

  private IsisSpfSmtEncoder() {}

  /**
   * Declares active interface costs as SpecLens {@code Config_*} fields and pins them to the parsed
   * snapshot. These fields belong to the control-plane encoding, not route guards or YU traffic.
   */
  static void initConfigurationConstants(
      Context ctx,
      Solver solver,
      Map<String, Expr> allVariables,
      Map<String, Configuration> configurations) {
    configurations.forEach(
        (hostname, configuration) ->
            configuration
                .getAllInterfaces(Configuration.DEFAULT_VRF_NAME)
                .values()
                .forEach(
                    iface -> {
                      if (iface.getIsis() == null) {
                        return;
                      }
                      initLevelCost(
                          ctx,
                          solver,
                          allVariables,
                          hostname,
                          iface,
                          IsisLevel.LEVEL_1,
                          iface.getIsis().getLevel1());
                      initLevelCost(
                          ctx,
                          solver,
                          allVariables,
                          hostname,
                          iface,
                          IsisLevel.LEVEL_2,
                          iface.getIsis().getLevel2());
                    }));
  }

  private static void initLevelCost(
      Context ctx,
      Solver solver,
      Map<String, Expr> allVariables,
      String hostname,
      Interface iface,
      IsisLevel level,
      IsisInterfaceLevelSettings settings) {
    if (settings == null || settings.getMode() != ACTIVE) {
      return;
    }
    String name = costVariable(hostname, iface.getName(), level);
    ArithExpr variable = ctx.mkIntConst(name);
    long pin = firstNonNull(settings.getCost(), IsisRoute.DEFAULT_METRIC);
    allVariables.put(variable.toString(), variable);
    solver.add(ctx.mkEq(variable, ctx.mkInt(pin)));
    solver.add(ctx.mkGe(variable, ctx.mkInt(0)));
    solver.add(ctx.mkLe(variable, ctx.mkInt(MAX_WIDE_METRIC)));
  }

  public static String costVariable(String hostname, String interfaceName, IsisLevel level) {
    if (level != IsisLevel.LEVEL_1 && level != IsisLevel.LEVEL_2) {
      throw new IllegalArgumentException("IS-IS cost variable requires L1 or L2");
    }
    return "Config_"
        + sanitize(hostname)
        + "_Interface_"
        + sanitize(interfaceName)
        + "_Isis_"
        + (level == IsisLevel.LEVEL_1 ? "L1" : "L2")
        + "_cost";
  }

  private static String sanitize(String raw) {
    return raw.replaceAll("[^A-Za-z0-9_]", "_");
  }
}
