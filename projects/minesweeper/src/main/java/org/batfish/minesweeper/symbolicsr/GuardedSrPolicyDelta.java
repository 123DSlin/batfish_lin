package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import javax.annotation.Nullable;

/**
 * Atomic semantic difference between two stable guarded SR-policy states.
 *
 * <p>The two update lists are a batch, not an imperative event stream: their iteration order has no
 * operational meaning. A stable key whose non-guard payload changes is {@link Type#REPLACED}. If
 * the stable key itself changes, the old and new objects are reported in this same batch as {@link
 * Type#REMOVED} and {@link Type#ADDED}; consumers must not pair unrelated additions and removals.
 */
public final class GuardedSrPolicyDelta {
  public enum Type {
    ADDED,
    REMOVED,
    GUARD_CHANGED,
    REPLACED
  }

  /**
   * One typed old/new lifecycle transition.
   *
   * <p>{@link Type#GUARD_CHANGED} preserves both stable identity and concrete payload. {@link
   * Type#REPLACED} preserves stable identity but changes concrete non-guard payload.
   */
  public static final class Update<T> {
    private final Type _type;
    @Nullable private final T _oldValue;
    @Nullable private final T _newValue;

    static <T> Update<T> added(T value) {
      return new Update<>(Type.ADDED, null, requireNonNull(value));
    }

    static <T> Update<T> removed(T value) {
      return new Update<>(Type.REMOVED, requireNonNull(value), null);
    }

    static <T> Update<T> changed(Type type, T oldValue, T newValue) {
      if (type != Type.GUARD_CHANGED && type != Type.REPLACED) {
        throw new IllegalArgumentException("change must be guard-only or replacement");
      }
      return new Update<>(type, requireNonNull(oldValue), requireNonNull(newValue));
    }

    private Update(Type type, @Nullable T oldValue, @Nullable T newValue) {
      _type = requireNonNull(type);
      _oldValue = oldValue;
      _newValue = newValue;
    }

    public Type getType() {
      return _type;
    }

    @Nullable
    public T getOldValue() {
      return _oldValue;
    }

    @Nullable
    public T getNewValue() {
      return _newValue;
    }
  }

  private final ImmutableList<Update<GuardedSrCandidate>> _candidateUpdates;
  private final ImmutableList<Update<GuardedSrPolicyContribution>> _contributionUpdates;

  GuardedSrPolicyDelta(
      Iterable<Update<GuardedSrCandidate>> candidateUpdates,
      Iterable<Update<GuardedSrPolicyContribution>> contributionUpdates) {
    _candidateUpdates = ImmutableList.copyOf(candidateUpdates);
    _contributionUpdates = ImmutableList.copyOf(contributionUpdates);
  }

  public ImmutableList<Update<GuardedSrCandidate>> getCandidateUpdates() {
    return _candidateUpdates;
  }

  public ImmutableList<Update<GuardedSrPolicyContribution>> getContributionUpdates() {
    return _contributionUpdates;
  }

  public boolean isEmpty() {
    return _candidateUpdates.isEmpty() && _contributionUpdates.isEmpty();
  }
}
