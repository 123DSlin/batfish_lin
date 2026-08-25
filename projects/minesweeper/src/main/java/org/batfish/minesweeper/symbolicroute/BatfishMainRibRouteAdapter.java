package org.batfish.minesweeper.symbolicroute;

import java.util.Comparator;
import java.util.Optional;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.dataplane.rib.Rib;

/**
 * Protocol-neutral adapter that delegates cross-protocol route preference to Batfish's main RIB.
 */
public final class BatfishMainRibRouteAdapter
    implements SymbolicRouteProtocolAdapter<AnnotatedRoute<AbstractRoute>> {

  @Nonnull private final Rib _preferenceOracle;

  public BatfishMainRibRouteAdapter() {
    _preferenceOracle = new Rib();
  }

  @Override
  public Comparator<AnnotatedRoute<AbstractRoute>> preferenceComparator(String receiver) {
    return (left, right) -> -Integer.signum(_preferenceOracle.comparePreference(left, right));
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<AbstractRoute>> processImport(
      SymbolicRouteMessage<AnnotatedRoute<AbstractRoute>> message) {
    AnnotatedRoute<AbstractRoute> route = message.getRoute();
    return message.getSessionId() == null && !route.getAbstractRoute().getNonRouting()
        ? Optional.of(route)
        : Optional.empty();
  }

  @Override
  @Nonnull
  public SymbolicRouteKey createCandidateKey(
      String receiver, AnnotatedRoute<AbstractRoute> importedRoute) {
    return new SymbolicRouteKey(receiver, importedRoute.getSourceVrf(), importedRoute);
  }

  @Override
  @Nonnull
  public Optional<AnnotatedRoute<AbstractRoute>> processExport(
      SymbolicRouteSession session, AnnotatedRoute<AbstractRoute> selectedRoute) {
    return Optional.empty();
  }

  @Override
  @Nonnull
  public String createExportMessageId(
      SymbolicRouteSession session, AnnotatedRoute<AbstractRoute> exportedRoute) {
    throw new IllegalStateException("main-RIB routes require explicit protocol redistribution");
  }
}
