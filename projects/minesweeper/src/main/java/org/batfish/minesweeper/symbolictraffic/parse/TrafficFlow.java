package org.batfish.minesweeper.symbolictraffic.parse;

import javax.annotation.Nullable;
import org.batfish.datamodel.Prefix;

/**
 * One incoming traffic demand {@code f} for YU Algorithm 1 {@code simulate(f)}.
 *
 * <p>This is the parsed traffic-layer analogue of a destination class / packet in Minesweeper: the
 * execution package never reads {@code traffic.json} itself.
 */
public class TrafficFlow {

  public enum ForwardingType {
    IP,
    SR_POLICY
  }

  /** Accepts {@code IP}, {@code SR_POLICY}, and the short alias {@code SR}. */
  public static ForwardingType parseForwardingType(String raw) {
    if (raw == null) {
      throw new IllegalArgumentException("forwarding type cannot be null");
    }
    String name = raw.trim().toUpperCase();
    if ("IP".equals(name)) {
      return ForwardingType.IP;
    }
    if ("SR".equals(name) || "SR_POLICY".equals(name)) {
      return ForwardingType.SR_POLICY;
    }
    throw new IllegalArgumentException("unsupported forwarding type: " + raw);
  }

  private final String _id;

  private final String _source;

  private final Prefix _destination;

  private final double _demandGbps;

  private final ForwardingType _forwarding;

  @Nullable private final Integer _color;

  @Nullable private final String _policy;

  public TrafficFlow(
      String id,
      String source,
      Prefix destination,
      double demandGbps,
      ForwardingType forwarding,
      @Nullable Integer color,
      @Nullable String policy) {
    _id = id;
    _source = source;
    _destination = destination;
    _demandGbps = demandGbps;
    _forwarding = forwarding;
    _color = color;
    _policy = policy;
  }

  public String getId() {
    return _id;
  }

  public String getSource() {
    return _source;
  }

  public Prefix getDestination() {
    return _destination;
  }

  public double getDemandGbps() {
    return _demandGbps;
  }

  public ForwardingType getForwarding() {
    return _forwarding;
  }

  @Nullable
  public Integer getColor() {
    return _color;
  }

  @Nullable
  public String getPolicy() {
    return _policy;
  }
}
