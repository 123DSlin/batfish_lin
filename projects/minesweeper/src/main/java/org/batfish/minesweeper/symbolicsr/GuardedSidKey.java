package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.Objects;
import org.batfish.datamodel.sr.SrSidBindingKey;

/** Stable identity of one SID binding as resolved from one node and VRF. */
public final class GuardedSidKey {
  private final String _resolverNode;
  private final String _resolverVrf;
  private final SrSidBindingKey _bindingKey;

  public GuardedSidKey(String resolverNode, String resolverVrf, SrSidBindingKey bindingKey) {
    _resolverNode = requireNonNull(resolverNode, "resolver node must be provided");
    _resolverVrf = requireNonNull(resolverVrf, "resolver VRF must be provided");
    _bindingKey = requireNonNull(bindingKey, "binding key must be provided");
  }

  public String getResolverNode() {
    return _resolverNode;
  }

  public String getResolverVrf() {
    return _resolverVrf;
  }

  public SrSidBindingKey getBindingKey() {
    return _bindingKey;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof GuardedSidKey)) {
      return false;
    }
    GuardedSidKey that = (GuardedSidKey) object;
    return _resolverNode.equals(that._resolverNode)
        && _resolverVrf.equals(that._resolverVrf)
        && _bindingKey.equals(that._bindingKey);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_resolverNode, _resolverVrf, _bindingKey);
  }
}
