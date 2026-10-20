package org.batfish.minesweeper.symbolictraffic.execution;

import javax.annotation.Nullable;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Prefix;
import org.batfish.minesweeper.symbolicroute.RouteGuard;
import org.batfish.minesweeper.symbolictraffic.parse.TrafficGraphEdge;

/**
 * One guarded RIB rule used by YU route selection and iteration.
 *
 * <p>A rule is a direct next hop ({@code l = nh_r}), an indirect next-hop IP {@code nip}, or a
 * terminal (local/discard) that matches the prefix but does not place traffic on a real link.
 * Lower {@code preference} is strictly better; longer prefixes are strictly better than shorter
 * ones, encoding LPM as part of {@code ≺}.
 *
 * <p>For a direct next hop, {@code availability} is the only link/route guard used when placing
 * traffic on that edge. Callers must encode next-hop/link failure in this guard. Adj-SID
 * forwarding additionally ANDs {@link SrPolicy.Segment#getAvailability()} and, if present, the
 * availability of a direct RIB rule for the same edge. Terminal rules still participate in {@code
 * s_r}/{@code c_r} so they can absorb locally delivered mass.
 */
public class ForwardingRule {

  private final Prefix _prefix;

  private final RouteGuard _availability;

  /**
   * Final guarded-RIB selection condition.
   *
   * <p>This is YU's {@code s_r}. It is deliberately separate from {@code availability}: the
   * former has already incorporated the protocol-specific, concrete route comparator (e.g., the
   * complete BGP best-path comparator), whereas the latter is only {@code g_r}.
   */
  private final RouteGuard _selection;

  private final int _preference;

  @Nullable private final TrafficGraphEdge _directNextHop;

  @Nullable private final Ip _indirectNextHop;

  private final boolean _terminal;

  public static ForwardingRule direct(
      Prefix prefix, RouteGuard availability, int preference, TrafficGraphEdge nextHop) {
    return direct(prefix, availability, availability, preference, nextHop);
  }

  /** Creates a direct rule whose protocol-specific selection guard has already been computed. */
  public static ForwardingRule direct(
      Prefix prefix,
      RouteGuard availability,
      RouteGuard selection,
      int preference,
      TrafficGraphEdge nextHop) {
    return new ForwardingRule(prefix, availability, selection, preference, nextHop, null, false);
  }

  public static ForwardingRule indirect(
      Prefix prefix, RouteGuard availability, int preference, Ip nextHopIp) {
    return indirect(prefix, availability, availability, preference, nextHopIp);
  }

  /** Creates an indirect rule whose protocol-specific selection guard has already been computed. */
  public static ForwardingRule indirect(
      Prefix prefix, RouteGuard availability, RouteGuard selection, int preference, Ip nextHopIp) {
    return new ForwardingRule(prefix, availability, selection, preference, null, nextHopIp, false);
  }

  /**
   * Local delivery or discard: the prefix matches and can win {@code ≺}, but {@code forward} does
   * not emit a real-link cell.
   */
  public static ForwardingRule terminal(Prefix prefix, RouteGuard availability, int preference) {
    return terminal(prefix, availability, availability, preference);
  }

  /** Creates a terminal rule whose protocol-specific selection guard has already been computed. */
  public static ForwardingRule terminal(
      Prefix prefix, RouteGuard availability, RouteGuard selection, int preference) {
    return new ForwardingRule(prefix, availability, selection, preference, null, null, true);
  }

  private ForwardingRule(
      Prefix prefix,
      RouteGuard availability,
      RouteGuard selection,
      int preference,
      @Nullable TrafficGraphEdge directNextHop,
      @Nullable Ip indirectNextHop,
      boolean terminal) {
    _prefix = prefix;
    _availability = availability;
    _selection = selection;
    _preference = preference;
    _directNextHop = directNextHop;
    _indirectNextHop = indirectNextHop;
    _terminal = terminal;
  }

  public Prefix getPrefix() {
    return _prefix;
  }

  public RouteGuard getAvailability() {
    return _availability;
  }

  /** Returns the YU selection guard. */
  public RouteGuard getSelection() {
    return _selection;
  }

  public int getPreference() {
    return _preference;
  }

  @Nullable
  public TrafficGraphEdge getDirectNextHop() {
    return _directNextHop;
  }

  @Nullable
  public Ip getIndirectNextHop() {
    return _indirectNextHop;
  }

  public boolean isIndirect() {
    return _indirectNextHop != null;
  }

  public boolean isTerminal() {
    return _terminal;
  }

  public ForwardingRule withAvailability(RouteGuard availability) {
    return new ForwardingRule(
        _prefix,
        availability,
        availability,
        _preference,
        _directNextHop,
        _indirectNextHop,
        _terminal);
  }

  public boolean matches(Ip dstIp) {
    return _prefix.containsIp(dstIp);
  }
}
