package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.Prefix6;

/** Typed IPv4/IPv6 prefix used by vendor-independent SR configuration. */
@ParametersAreNonnullByDefault
public final class SrPrefix implements Serializable {
  public enum Family {
    IPV4,
    IPV6
  }

  private static final String PROP_FAMILY = "family";
  private static final String PROP_IPV4 = "ipv4";
  private static final String PROP_IPV6 = "ipv6";

  private final Family _family;
  @Nullable private final Prefix _ipv4;
  @Nullable private final Prefix6 _ipv6;

  @JsonCreator
  private static SrPrefix create(
      @Nullable @JsonProperty(PROP_FAMILY) Family family,
      @Nullable @JsonProperty(PROP_IPV4) Prefix ipv4,
      @Nullable @JsonProperty(PROP_IPV6) Prefix6 ipv6) {
    checkArgument(family != null, "Missing %s", PROP_FAMILY);
    return new SrPrefix(family, ipv4, ipv6);
  }

  public static SrPrefix ipv4(Prefix prefix) {
    return new SrPrefix(Family.IPV4, prefix, null);
  }

  public static SrPrefix ipv6(Prefix6 prefix) {
    return new SrPrefix(Family.IPV6, null, prefix);
  }

  private SrPrefix(Family family, @Nullable Prefix ipv4, @Nullable Prefix6 ipv6) {
    checkArgument((family == Family.IPV4) == (ipv4 != null), "IPv4 family/value mismatch");
    checkArgument((family == Family.IPV6) == (ipv6 != null), "IPv6 family/value mismatch");
    _family = family;
    _ipv4 = ipv4;
    _ipv6 = ipv6;
  }

  @JsonProperty(PROP_FAMILY)
  public Family getFamily() {
    return _family;
  }

  @Nullable
  @JsonProperty(PROP_IPV4)
  public Prefix getIpv4() {
    return _ipv4;
  }

  @Nullable
  @JsonProperty(PROP_IPV6)
  public Prefix6 getIpv6() {
    return _ipv6;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) return true;
    if (!(o instanceof SrPrefix)) return false;
    SrPrefix that = (SrPrefix) o;
    return _family == that._family
        && Objects.equals(_ipv4, that._ipv4)
        && Objects.equals(_ipv6, that._ipv6);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_family, _ipv4, _ipv6);
  }
}
