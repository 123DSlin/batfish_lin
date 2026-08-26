package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRouteDecorator;

/**
 * Builds a symbolic route convergence network from protocol-neutral routers, sessions, and seeds.
 */
public final class SymbolicRouteNetworkFactory {

  private SymbolicRouteNetworkFactory() {}

  @Nonnull
  public static <R extends AbstractRouteDecorator> SymbolicRouteNetwork<R> create(
      Iterable<String> routers,
      Iterable<SymbolicRouteSession> sessions,
      Iterable<SymbolicRouteSeed<R>> seeds,
      SymbolicRouteProtocolAdapter<R> adapter) {
    requireNonNull(routers, "routers must be provided");
    requireNonNull(sessions, "sessions must be provided");
    requireNonNull(seeds, "seeds must be provided");
    requireNonNull(adapter, "adapter must be provided");
    Map<String, GuardedRib<R>> ribs = new LinkedHashMap<>();
    List<SymbolicRouteIngressProcessor<R>> processors = new ArrayList<>();
    for (String router : routers) {
      String checkedRouter = requireNonNull(router, "router must be provided");
      if (ribs.containsKey(checkedRouter)) {
        throw new IllegalArgumentException("duplicate symbolic router");
      }
      GuardedRib<R> rib =
          new GuardedRib<>(
              requireNonNull(
                  adapter.preferenceComparator(checkedRouter),
                  "adapter preference comparator must be provided"));
      ribs.put(checkedRouter, rib);
      processors.add(
          new SymbolicRouteIngressProcessor<>(
              checkedRouter, rib, adapter::processImport, adapter::createCandidateKey));
    }
    SymbolicRoutePropagationDependencies dependencies = new SymbolicRoutePropagationDependencies();
    List<SymbolicRouteExporter<R>> exporters = new ArrayList<>();
    Set<String> sessionIds = new LinkedHashSet<>();
    for (SymbolicRouteSession session : sessions) {
      SymbolicRouteSession checkedSession = requireNonNull(session, "session must be provided");
      if (!ribs.containsKey(checkedSession.getSender())
          || !ribs.containsKey(checkedSession.getReceiver())) {
        throw new IllegalArgumentException("session endpoints must be registered routers");
      }
      if (!sessionIds.add(checkedSession.getSessionId())) {
        throw new IllegalArgumentException("duplicate symbolic route session identity");
      }
      exporters.add(
          new SymbolicRouteExporter<>(
              checkedSession.getSender(),
              checkedSession.getReceiver(),
              checkedSession.getSessionId(),
              checkedSession.getLinkGuard(),
              (sender, receiver, route) -> adapter.processExport(checkedSession, route),
              (sender, receiver, candidateKey, route) ->
                  namespaceMessageId(
                      checkedSession.getSessionId(),
                      requireNonNull(
                          adapter.createExportMessageId(checkedSession, candidateKey, route),
                          "adapter export message identity must be provided")),
              dependencies));
    }
    List<SymbolicRouteMessage<R>> advertisements = new ArrayList<>();
    Set<SymbolicRouteContributionId> seedIds = new LinkedHashSet<>();
    for (SymbolicRouteSeed<R> seed : seeds) {
      SymbolicRouteSeed<R> checkedSeed = requireNonNull(seed, "seed must be provided");
      if (!ribs.containsKey(checkedSeed.getOriginRouter())) {
        throw new IllegalArgumentException("seed origin must be a registered router");
      }
      SymbolicRouteContributionId seedId =
          new SymbolicRouteContributionId(
              checkedSeed.getMessageId(),
              checkedSeed.getOriginRouter(),
              checkedSeed.getOriginRouter());
      if (!seedIds.add(seedId)) {
        throw new IllegalArgumentException("duplicate symbolic route seed identity");
      }
      advertisements.add(checkedSeed.toMessage());
    }
    return new SymbolicRouteNetwork<>(
        new SymbolicRouteConvergenceEngine<>(processors, exporters),
        ribs,
        advertisements,
        dependencies);
  }

  private static String namespaceMessageId(String sessionId, String adapterMessageId) {
    return String.format("%d:%s:%s", sessionId.length(), sessionId, adapterMessageId);
  }
}
