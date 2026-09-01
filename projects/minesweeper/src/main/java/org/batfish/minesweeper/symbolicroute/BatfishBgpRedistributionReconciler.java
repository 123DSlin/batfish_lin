package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import javax.annotation.Nonnull;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.BgpProcess;
import org.batfish.datamodel.Bgpv4Route;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.RoutingProtocol;
import org.batfish.datamodel.Vrf;

/** Reconciles selected connected/static MAIN branches into local guarded BGP contributions. */
public final class BatfishBgpRedistributionReconciler {

  private static final class SourceKey {
    @Nonnull private final String _ruleId;
    @Nonnull private final SymbolicRouteKey _routeKey;

    private SourceKey(String ruleId, SymbolicRouteKey routeKey) {
      _ruleId = ruleId;
      _routeKey = routeKey;
    }

    @Override
    public boolean equals(Object object) {
      if (this == object) {
        return true;
      }
      if (!(object instanceof SourceKey)) {
        return false;
      }
      SourceKey that = (SourceKey) object;
      return _ruleId.equals(that._ruleId) && _routeKey.equals(that._routeKey);
    }

    @Override
    public int hashCode() {
      return Objects.hash(_ruleId, _routeKey);
    }
  }

  private static final class Desired {
    @Nonnull private final BatfishRoutingPolicyResult<Bgpv4Route> _policyResult;
    @Nonnull private final RouteGuard _guard;

    private Desired(BatfishRoutingPolicyResult<Bgpv4Route> policyResult, RouteGuard guard) {
      _policyResult = policyResult;
      _guard = guard;
    }
  }

  @Nonnull private final Map<String, Configuration> _configurations;
  @Nonnull private final Iterable<BatfishBgpRedistributionRule> _rules;
  @Nonnull private final SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> _mainNetwork;
  @Nonnull private final BatfishRedistributionReconciler<Bgpv4Route> _routeReconciler;
  @Nonnull private final Map<SourceKey, BatfishRedistributionKey> _identities;
  @Nonnull private final Map<SourceKey, RouteGuard> _lastGuards;
  @Nonnull private SymbolicRouteConvergenceResult _lastConvergence;
  private boolean _started;
  private boolean _reconciling;
  private boolean _pending;

  public BatfishBgpRedistributionReconciler(
      Map<String, Configuration> configurations,
      Iterable<BatfishBgpRedistributionRule> rules,
      SymbolicRouteNetwork<AnnotatedRoute<AbstractRoute>> mainNetwork,
      SymbolicRouteNetwork<AnnotatedRoute<Bgpv4Route>> bgpNetwork) {
    _configurations = requireNonNull(configurations, "configurations must be provided");
    _rules = requireNonNull(rules, "rules must be provided");
    _mainNetwork = requireNonNull(mainNetwork, "mainNetwork must be provided");
    _routeReconciler = new BatfishRedistributionReconciler<>(bgpNetwork);
    _identities = new LinkedHashMap<>();
    _lastGuards = new LinkedHashMap<>();
    _lastConvergence = emptyResult();
  }

  /** Registers the MAIN stable-state callback and reconciles the current snapshot. */
  public void start() {
    if (_started) {
      throw new IllegalStateException("BGP redistribution reconciler is already started");
    }
    _started = true;
    _mainNetwork.getEngine().addStableStateListener(this::reconcile);
    reconcile();
  }

  /** Recomputes deterministic Batfish policy outcomes and applies their semantic delta to BGP. */
  public void reconcile() {
    if (_reconciling) {
      _pending = true;
      return;
    }
    _reconciling = true;
    int messages = 0;
    int withdrawals = 0;
    int updates = 0;
    try {
      do {
        _pending = false;
        Map<SourceKey, Desired> desired = collectDesired();
        for (Map.Entry<SourceKey, BatfishRedistributionKey> known : _identities.entrySet()) {
          if (!desired.containsKey(known.getKey())) {
            SymbolicRouteConvergenceResult result =
                _routeReconciler.reconcile(
                    known.getValue(),
                    BatfishRoutingPolicyResult.denied(),
                    _lastGuards.get(known.getKey()));
            messages += result.getProcessedMessages();
            withdrawals += result.getProcessedWithdrawals();
            updates += result.getRibUpdates();
          }
        }
        for (Map.Entry<SourceKey, Desired> entry : desired.entrySet()) {
          Desired value = entry.getValue();
          _lastGuards.put(entry.getKey(), value._guard);
          SymbolicRouteConvergenceResult result =
              _routeReconciler.reconcile(
                  identity(entry.getKey()), value._policyResult, value._guard);
          messages += result.getProcessedMessages();
          withdrawals += result.getProcessedWithdrawals();
          updates += result.getRibUpdates();
        }
      } while (_pending);
    } finally {
      _reconciling = false;
    }
    _lastConvergence = new SymbolicRouteConvergenceResult(messages, withdrawals, updates);
  }

  @Nonnull
  public SymbolicRouteConvergenceResult getLastConvergence() {
    return _lastConvergence;
  }

  private Map<SourceKey, Desired> collectDesired() {
    Map<SourceKey, Desired> desired = new LinkedHashMap<>();
    for (BatfishBgpRedistributionRule rule : _rules) {
      Configuration configuration = _configurations.get(rule.getRouter());
      BgpProcess process = bgpProcess(configuration, rule.getTargetVrf());
      for (GuardedRibEntry<AnnotatedRoute<AbstractRoute>> entry :
          _mainNetwork.getRib(rule.getRouter()).getEntries()) {
        SymbolicRoute<AnnotatedRoute<AbstractRoute>> symbolic = entry.getSymbolicRoute();
        RoutingProtocol sourceProtocol = symbolic.getKey().getProtocol();
        if (!symbolic.getKey().getVrf().equals(rule.getSourceVrf())
            || sourceProtocol == RoutingProtocol.BGP
            || sourceProtocol == RoutingProtocol.IBGP
            || !entry.getSelectionGuard().isSatisfiable()) {
          continue;
        }
        BatfishRoutingPolicyResult<Bgpv4Route> converted =
            BatfishBgpRedistribution.redistribute(
                configuration,
                process,
                rule.getPolicyName(),
                symbolic.getRoute(),
                rule.getTargetVrf(),
                rule.getTargetProtocol());
        if (converted.getOutcome() == BatfishRoutingPolicyResult.Outcome.POLICY_NOT_FOUND) {
          throw new IllegalArgumentException(
              "redistribution policy is missing: " + rule.getPolicyName());
        }
        desired.put(
            new SourceKey(rule.getRuleId(), symbolic.getKey()),
            new Desired(converted, entry.getSelectionGuard()));
      }
    }
    return desired;
  }

  private BatfishRedistributionKey identity(SourceKey source) {
    BatfishRedistributionKey old = _identities.get(source);
    if (old != null) {
      return old;
    }
    BatfishBgpRedistributionRule rule = rule(source._ruleId);
    BatfishRedistributionKey created =
        new BatfishRedistributionKey(
            "main-source-" + _identities.size(),
            rule.getRouter(),
            rule.getSourceVrf(),
            rule.getTargetVrf(),
            source._routeKey.getProtocol(),
            rule.getTargetProtocol(),
            rule.getPolicyName());
    _identities.put(source, created);
    return created;
  }

  private BatfishBgpRedistributionRule rule(String ruleId) {
    for (BatfishBgpRedistributionRule rule : _rules) {
      if (rule.getRuleId().equals(ruleId)) {
        return rule;
      }
    }
    throw new IllegalStateException("registered redistribution rule disappeared");
  }

  private static BgpProcess bgpProcess(Configuration configuration, String vrfName) {
    Vrf vrf = configuration.getVrfs().get(vrfName);
    if (vrf == null || vrf.getBgpProcess() == null) {
      throw new IllegalArgumentException("redistribution target VRF must have a BGP process");
    }
    return vrf.getBgpProcess();
  }

  private static SymbolicRouteConvergenceResult emptyResult() {
    return new SymbolicRouteConvergenceResult(0, 0, 0);
  }
}
