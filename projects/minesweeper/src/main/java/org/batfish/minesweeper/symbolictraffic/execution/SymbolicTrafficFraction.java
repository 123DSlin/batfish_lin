package org.batfish.minesweeper.symbolictraffic.execution;

/**
 * One cell of {@code M[l, S]}: the symbolic traffic fraction Algorithm 1 adds together.
 *
 * <p>Algorithm 1 only needs {@code 0}, {@code 1}, and addition (incoming {@code ω} and {@code M_i
 * += forward(...)}). Algorithm 2 will later put failure-variable formulas in this cell; the
 * current representation is a constant, which is exactly what {@code M0[l_R, ∅] ← 1} requires.
 */
public class SymbolicTrafficFraction {

  private static final SymbolicTrafficFraction ZERO = new SymbolicTrafficFraction(0.0);
  private static final SymbolicTrafficFraction ONE = new SymbolicTrafficFraction(1.0);

  private final double _value;

  public SymbolicTrafficFraction(double value) {
    _value = value;
  }

  public static SymbolicTrafficFraction zero() {
    return ZERO;
  }

  public static SymbolicTrafficFraction one() {
    return ONE;
  }

  public SymbolicTrafficFraction plus(SymbolicTrafficFraction other) {
    if (isZero()) {
      return other;
    }
    if (other.isZero()) {
      return this;
    }
    return new SymbolicTrafficFraction(_value + other._value);
  }

  public boolean isZero() {
    return _value == 0.0;
  }

  public boolean isOne() {
    return _value == 1.0;
  }

  public double getValue() {
    return _value;
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicTrafficFraction)) {
      return false;
    }
    return Double.compare(_value, ((SymbolicTrafficFraction) o)._value) == 0;
  }

  @Override
  public int hashCode() {
    return Double.hashCode(_value);
  }

  @Override
  public String toString() {
    return Double.toString(_value);
  }
}
