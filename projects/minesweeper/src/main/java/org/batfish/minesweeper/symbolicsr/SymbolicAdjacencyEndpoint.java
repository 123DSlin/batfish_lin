package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import java.util.Objects;

/** Directed endpoint reached after executing one local adjacency SID. */
public final class SymbolicAdjacencyEndpoint {
  private final String _node;
  private final String _vrf;
  private final String _interfaceName;

  public SymbolicAdjacencyEndpoint(String node, String vrf, String interfaceName) {
    _node = requireNonNull(node, "node must be provided");
    _vrf = requireNonNull(vrf, "VRF must be provided");
    _interfaceName = requireNonNull(interfaceName, "interface must be provided");
  }

  public String getNode() {
    return _node;
  }

  public String getVrf() {
    return _vrf;
  }

  public String getInterfaceName() {
    return _interfaceName;
  }

  @Override
  public boolean equals(Object object) {
    if (this == object) {
      return true;
    }
    if (!(object instanceof SymbolicAdjacencyEndpoint)) {
      return false;
    }
    SymbolicAdjacencyEndpoint that = (SymbolicAdjacencyEndpoint) object;
    return _node.equals(that._node)
        && _vrf.equals(that._vrf)
        && _interfaceName.equals(that._interfaceName);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_node, _vrf, _interfaceName);
  }
}
