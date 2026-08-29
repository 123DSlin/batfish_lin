package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import java.util.Map;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.GenericRibReadOnly;
import org.batfish.datamodel.IsisRoute;

/** Normalized, strongly typed input for one whole-network symbolic route computation. */
public final class BatfishSymbolicRoutePipelineInput {

  @Nonnull private final ImmutableMap<String, Configuration> _configurations;
  @Nonnull private final ImmutableList<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> _mainSeeds;
  @Nonnull private final ImmutableList<SymbolicStaticRoute> _recursiveStaticRoutes;
  @Nonnull private final ImmutableList<BatfishBgpRedistributionRule> _redistributionRules;
  @Nonnull private final ImmutableList<BatfishBgpEdge> _bgpEdges;
  @Nonnull private final ImmutableList<SymbolicRouteSession> _bgpSessions;
  @Nonnull private final ImmutableList<BatfishIsisEdge> _isisEdges;
  @Nonnull private final ImmutableList<SymbolicRouteSession> _isisSessions;
  @Nonnull private final ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> _isisSeeds;

  @Nonnull
  private final ImmutableMap<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
      _concreteMainRibs;

  public BatfishSymbolicRoutePipelineInput(
      Map<String, Configuration> configurations,
      Iterable<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> mainSeeds,
      Iterable<SymbolicStaticRoute> recursiveStaticRoutes,
      Iterable<BatfishBgpRedistributionRule> redistributionRules,
      Iterable<BatfishBgpEdge> bgpEdges,
      Iterable<SymbolicRouteSession> bgpSessions,
      Map<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs) {
    this(
        configurations,
        mainSeeds,
        recursiveStaticRoutes,
        redistributionRules,
        bgpEdges,
        bgpSessions,
        ImmutableList.of(),
        ImmutableList.of(),
        ImmutableList.of(),
        concreteMainRibs);
  }

  public BatfishSymbolicRoutePipelineInput(
      Map<String, Configuration> configurations,
      Iterable<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> mainSeeds,
      Iterable<SymbolicStaticRoute> recursiveStaticRoutes,
      Iterable<BatfishBgpRedistributionRule> redistributionRules,
      Iterable<BatfishBgpEdge> bgpEdges,
      Iterable<SymbolicRouteSession> bgpSessions,
      Iterable<BatfishIsisEdge> isisEdges,
      Iterable<SymbolicRouteSession> isisSessions,
      Iterable<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> isisSeeds,
      Map<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
          concreteMainRibs) {
    _configurations =
        ImmutableMap.copyOf(requireNonNull(configurations, "configurations must be provided"));
    _mainSeeds = ImmutableList.copyOf(requireNonNull(mainSeeds, "mainSeeds must be provided"));
    _recursiveStaticRoutes =
        ImmutableList.copyOf(
            requireNonNull(recursiveStaticRoutes, "recursiveStaticRoutes must be provided"));
    _redistributionRules =
        ImmutableList.copyOf(
            requireNonNull(redistributionRules, "redistributionRules must be provided"));
    _bgpEdges = ImmutableList.copyOf(requireNonNull(bgpEdges, "bgpEdges must be provided"));
    _bgpSessions =
        ImmutableList.copyOf(requireNonNull(bgpSessions, "bgpSessions must be provided"));
    _isisEdges = ImmutableList.copyOf(requireNonNull(isisEdges, "isisEdges must be provided"));
    _isisSessions =
        ImmutableList.copyOf(requireNonNull(isisSessions, "isisSessions must be provided"));
    _isisSeeds = ImmutableList.copyOf(requireNonNull(isisSeeds, "isisSeeds must be provided"));
    ImmutableMap.Builder<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
        ribs = ImmutableMap.builder();
    requireNonNull(concreteMainRibs, "concreteMainRibs must be provided")
        .forEach((router, byVrf) -> ribs.put(router, ImmutableMap.copyOf(byVrf)));
    _concreteMainRibs = ribs.build();
  }

  @Nonnull
  public ImmutableMap<String, Configuration> getConfigurations() {
    return _configurations;
  }

  @Nonnull
  public ImmutableList<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> getMainSeeds() {
    return _mainSeeds;
  }

  @Nonnull
  public ImmutableList<SymbolicStaticRoute> getRecursiveStaticRoutes() {
    return _recursiveStaticRoutes;
  }

  @Nonnull
  public ImmutableList<BatfishBgpRedistributionRule> getRedistributionRules() {
    return _redistributionRules;
  }

  @Nonnull
  public ImmutableList<BatfishBgpEdge> getBgpEdges() {
    return _bgpEdges;
  }

  @Nonnull
  public ImmutableList<SymbolicRouteSession> getBgpSessions() {
    return _bgpSessions;
  }

  @Nonnull
  public ImmutableList<BatfishIsisEdge> getIsisEdges() {
    return _isisEdges;
  }

  @Nonnull
  public ImmutableList<SymbolicRouteSession> getIsisSessions() {
    return _isisSessions;
  }

  @Nonnull
  public ImmutableList<SymbolicRouteSeed<AnnotatedRoute<IsisRoute>>> getIsisSeeds() {
    return _isisSeeds;
  }

  @Nonnull
  public ImmutableMap<String, Map<String, GenericRibReadOnly<AnnotatedRoute<AbstractRoute>>>>
      getConcreteMainRibs() {
    return _concreteMainRibs;
  }
}
