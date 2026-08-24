package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRouteDecorator;

/** An immutable, validated change to a guarded candidate RIB. */
public final class SymbolicRibUpdate<R extends AbstractRouteDecorator> {

  @Nonnull private final SymbolicRibUpdateType _type;
  @Nullable private final SymbolicRoute<R> _oldRoute;
  @Nullable private final SymbolicRoute<R> _newRoute;

  private SymbolicRibUpdate(
      SymbolicRibUpdateType type,
      @Nullable SymbolicRoute<R> oldRoute,
      @Nullable SymbolicRoute<R> newRoute) {
    _type = requireNonNull(type, "type must be provided");
    _oldRoute = oldRoute;
    _newRoute = newRoute;
    validate();
  }

  public static <R extends AbstractRouteDecorator> SymbolicRibUpdate<R> added(
      SymbolicRoute<R> route) {
    return new SymbolicRibUpdate<>(SymbolicRibUpdateType.ADDED, null, route);
  }

  public static <R extends AbstractRouteDecorator> SymbolicRibUpdate<R> removed(
      SymbolicRoute<R> route) {
    return new SymbolicRibUpdate<>(SymbolicRibUpdateType.REMOVED, route, null);
  }

  public static <R extends AbstractRouteDecorator> SymbolicRibUpdate<R> availabilityGuardChanged(
      SymbolicRoute<R> oldRoute, SymbolicRoute<R> newRoute) {
    return new SymbolicRibUpdate<>(
        SymbolicRibUpdateType.AVAILABILITY_GUARD_CHANGED, oldRoute, newRoute);
  }

  private void validate() {
    switch (_type) {
      case ADDED:
        if (_oldRoute != null || _newRoute == null) {
          throw new IllegalArgumentException("ADDED update requires only a new route");
        }
        break;
      case REMOVED:
        if (_oldRoute == null || _newRoute != null) {
          throw new IllegalArgumentException("REMOVED update requires only an old route");
        }
        break;
      case AVAILABILITY_GUARD_CHANGED:
        if (_oldRoute == null || _newRoute == null) {
          throw new IllegalArgumentException("guard change requires old and new routes");
        }
        if (!_oldRoute.getKey().equals(_newRoute.getKey())) {
          throw new IllegalArgumentException("guard change routes must have the same key");
        }
        break;
      default:
        throw new IllegalArgumentException("Unsupported update type: " + _type);
    }
  }

  @Nonnull
  public SymbolicRibUpdateType getType() {
    return _type;
  }

  @Nullable
  public SymbolicRoute<R> getOldRoute() {
    return _oldRoute;
  }

  @Nullable
  public SymbolicRoute<R> getNewRoute() {
    return _newRoute;
  }
}
