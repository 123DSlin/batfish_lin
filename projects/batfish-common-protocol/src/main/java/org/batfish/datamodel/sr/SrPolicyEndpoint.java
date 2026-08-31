package org.batfish.datamodel.sr;

import static com.google.common.base.Preconditions.checkArgument;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.io.Serializable;
import java.util.Objects;
import javax.annotation.Nullable;
import javax.annotation.ParametersAreNonnullByDefault;
import org.batfish.datamodel.Ip;
import org.batfish.datamodel.Ip6;

/** Typed IPv4/IPv6 endpoint used in an SR policy identity. */
@ParametersAreNonnullByDefault
public final class SrPolicyEndpoint implements Serializable {
  public enum Family {
    IPV4,
    IPV6
  }

  private static final String PROP_FAMILY = "family";
  private static final String PROP_IPV4 = "ipv4";
  private static final String PROP_IPV6 = "ipv6";

  private final Family _family;
  @Nullable private final Ip _ipv4;
  @Nullable private final Ip6 _ipv6;

  @JsonCreator
  private static SrPolicyEndpoint create(
      @Nullable @JsonProperty(PROP_FAMILY) Family family,
      @Nullable @JsonProperty(PROP_IPV4) Ip ipv4,
      @Nullable @JsonProperty(PROP_IPV6) Ip6 ipv6) {
    checkArgument(family != null, "SR policy endpoint family must be provided");
    return new SrPolicyEndpoint(family, ipv4, ipv6);
  }

  public static SrPolicyEndpoint ipv4(Ip endpoint) {
    return new SrPolicyEndpoint(Family.IPV4, endpoint, null);
  }

  public static SrPolicyEndpoint ipv6(Ip6 endpoint) {
    return new SrPolicyEndpoint(Family.IPV6, null, endpoint);
  }

  private SrPolicyEndpoint(Family family, @Nullable Ip ipv4, @Nullable Ip6 ipv6) {
    checkArgument((family == Family.IPV4) == (ipv4 != null), "IPv4 endpoint value mismatch");
    checkArgument((family == Family.IPV6) == (ipv6 != null), "IPv6 endpoint value mismatch");
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
  public Ip getIpv4() {
    return _ipv4;
  }

  @Nullable
  @JsonProperty(PROP_IPV6)
  public Ip6 getIpv6() {
    return _ipv6;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SrPolicyEndpoint)) {
      return false;
    }
    SrPolicyEndpoint that = (SrPolicyEndpoint) object;
    return _family == that._family
        && Objects.equals(_ipv4, that._ipv4)
        && Objects.equals(_ipv6, that._ipv6);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_family, _ipv4, _ipv6);
  }
}
