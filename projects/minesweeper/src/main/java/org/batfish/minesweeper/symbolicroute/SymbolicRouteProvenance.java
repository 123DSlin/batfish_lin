package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.List;
import java.util.Objects;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;

/** Immutable provenance for a route derived during symbolic propagation. */
public final class SymbolicRouteProvenance {

  @Nonnull private final String _originRouter;
  @Nonnull private final String _currentRouter;
  @Nullable private final String _previousRouter;
  @Nullable private final String _incomingInterface;
  @Nonnull private final List<String> _routerPath;
  @Nullable private final String _parentMessageId;

  public SymbolicRouteProvenance(
      String originRouter,
      String currentRouter,
      @Nullable String previousRouter,
      @Nullable String incomingInterface,
      List<String> routerPath,
      @Nullable String parentMessageId) {
    _originRouter = requireNonNull(originRouter, "originRouter must be provided");
    _currentRouter = requireNonNull(currentRouter, "currentRouter must be provided");
    _previousRouter = previousRouter;
    _incomingInterface = incomingInterface;
    _routerPath = ImmutableList.copyOf(requireNonNull(routerPath, "routerPath must be provided"));
    _parentMessageId = parentMessageId;
    if (_routerPath.isEmpty() || !_routerPath.get(0).equals(_originRouter)) {
      throw new IllegalArgumentException("routerPath must begin with originRouter");
    }
    if (!_routerPath.get(_routerPath.size() - 1).equals(_currentRouter)) {
      throw new IllegalArgumentException("routerPath must end with currentRouter");
    }
  }

  @Nonnull
  public String getOriginRouter() {
    return _originRouter;
  }

  @Nonnull
  public String getCurrentRouter() {
    return _currentRouter;
  }

  @Nullable
  public String getPreviousRouter() {
    return _previousRouter;
  }

  @Nullable
  public String getIncomingInterface() {
    return _incomingInterface;
  }

  @Nonnull
  public List<String> getRouterPath() {
    return _routerPath;
  }

  @Nullable
  public String getParentMessageId() {
    return _parentMessageId;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicRouteProvenance)) {
      return false;
    }
    SymbolicRouteProvenance that = (SymbolicRouteProvenance) o;
    return _originRouter.equals(that._originRouter)
        && _currentRouter.equals(that._currentRouter)
        && Objects.equals(_previousRouter, that._previousRouter)
        && Objects.equals(_incomingInterface, that._incomingInterface)
        && _routerPath.equals(that._routerPath)
        && Objects.equals(_parentMessageId, that._parentMessageId);
  }

  @Override
  public int hashCode() {
    return Objects.hash(
        _originRouter,
        _currentRouter,
        _previousRouter,
        _incomingInterface,
        _routerPath,
        _parentMessageId);
  }
}
