package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableMap;
import java.util.Map;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;

/** Canonical link identities and aliveness guards indexed by parsed router interface. */
public final class TopologyLinkGuards {

  @Nonnull private final ImmutableMap<String, LinkFailureKey> _keysByEndpoint;
  @Nonnull private final ImmutableMap<LinkFailureKey, RouteGuard> _guardsByKey;

  TopologyLinkGuards(
      Map<String, LinkFailureKey> keysByEndpoint, Map<LinkFailureKey, RouteGuard> guardsByKey) {
    _keysByEndpoint = ImmutableMap.copyOf(requireNonNull(keysByEndpoint));
    _guardsByKey = ImmutableMap.copyOf(requireNonNull(guardsByKey));
  }

  @Nullable
  public LinkFailureKey getKey(String router, String iface) {
    return _keysByEndpoint.get(endpoint(router, iface));
  }

  @Nullable
  public RouteGuard getGuard(String router, String iface) {
    LinkFailureKey key = getKey(router, iface);
    return key == null ? null : _guardsByKey.get(key);
  }

  @Nonnull
  public ImmutableMap<String, LinkFailureKey> getKeysByEndpoint() {
    return _keysByEndpoint;
  }

  @Nonnull
  public ImmutableMap<LinkFailureKey, RouteGuard> getGuardsByKey() {
    return _guardsByKey;
  }

  static String endpoint(String router, String iface) {
    return requireNonNull(router) + ":" + requireNonNull(iface);
  }
}
