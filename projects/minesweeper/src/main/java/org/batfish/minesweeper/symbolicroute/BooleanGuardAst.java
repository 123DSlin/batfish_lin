package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableSet;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;

/** Solver-independent, canonical Boolean syntax tree for persisted symbolic guards. */
public final class BooleanGuardAst {

  public enum Operator {
    TRUE,
    FALSE,
    VARIABLE,
    NOT,
    AND,
    OR
  }

  @Nonnull private final Operator _operator;
  @Nullable private final String _variableId;
  @Nonnull private final ImmutableList<BooleanGuardAst> _children;

  @JsonCreator
  private static BooleanGuardAst create(
      @JsonProperty("operator") Operator operator,
      @Nullable @JsonProperty("variableId") String variableId,
      @Nullable @JsonProperty("children") List<BooleanGuardAst> children) {
    Operator checkedOperator = requireNonNull(operator, "operator must be provided");
    List<BooleanGuardAst> checkedChildren = firstNonNull(children, ImmutableList.of());
    switch (checkedOperator) {
      case TRUE:
        return trueValue();
      case FALSE:
        return falseValue();
      case VARIABLE:
        return variable(requireNonNull(variableId, "VARIABLE requires variableId"));
      case NOT:
        if (checkedChildren.size() != 1) {
          throw new IllegalArgumentException("NOT requires exactly one child");
        }
        return not(checkedChildren.get(0));
      case AND:
        return and(checkedChildren);
      case OR:
        return or(checkedChildren);
      default:
        throw new IllegalArgumentException("unsupported Boolean guard operator");
    }
  }

  private BooleanGuardAst(
      Operator operator, @Nullable String variableId, Iterable<BooleanGuardAst> children) {
    _operator = requireNonNull(operator, "operator must be provided");
    _variableId = variableId;
    _children = ImmutableList.copyOf(requireNonNull(children, "children must be provided"));
  }

  public static BooleanGuardAst trueValue() {
    return new BooleanGuardAst(Operator.TRUE, null, ImmutableList.of());
  }

  public static BooleanGuardAst falseValue() {
    return new BooleanGuardAst(Operator.FALSE, null, ImmutableList.of());
  }

  public static BooleanGuardAst variable(String variableId) {
    String checked = requireNonNull(variableId, "variableId must be provided");
    if (checked.isEmpty()) {
      throw new IllegalArgumentException("variableId must not be empty");
    }
    return new BooleanGuardAst(Operator.VARIABLE, checked, ImmutableList.of());
  }

  public static BooleanGuardAst not(BooleanGuardAst child) {
    return new BooleanGuardAst(
        Operator.NOT, null, ImmutableList.of(requireNonNull(child, "NOT child must be provided")));
  }

  public static BooleanGuardAst and(BooleanGuardAst left, BooleanGuardAst right) {
    return and(ImmutableList.of(left, right));
  }

  public static BooleanGuardAst and(Iterable<BooleanGuardAst> children) {
    return associative(Operator.AND, children);
  }

  public static BooleanGuardAst or(BooleanGuardAst left, BooleanGuardAst right) {
    return or(ImmutableList.of(left, right));
  }

  public static BooleanGuardAst or(Iterable<BooleanGuardAst> children) {
    return associative(Operator.OR, children);
  }

  private static BooleanGuardAst associative(
      Operator operator, Iterable<BooleanGuardAst> children) {
    List<BooleanGuardAst> flattened = new ArrayList<>();
    for (BooleanGuardAst child : requireNonNull(children, "children must be provided")) {
      BooleanGuardAst checked = requireNonNull(child, "child must be provided");
      if (checked._operator == operator) {
        flattened.addAll(checked._children);
      } else {
        flattened.add(checked);
      }
    }
    flattened.sort(Comparator.comparing(BooleanGuardAst::canonicalForm));
    Set<BooleanGuardAst> unique = new LinkedHashSet<>(flattened);
    if (unique.isEmpty()) {
      return operator == Operator.AND ? trueValue() : falseValue();
    }
    if (unique.size() == 1) {
      return unique.iterator().next();
    }
    return new BooleanGuardAst(operator, null, unique);
  }

  @JsonProperty("operator")
  @Nonnull
  public Operator getOperator() {
    return _operator;
  }

  @JsonProperty("variableId")
  @Nullable
  public String getVariableId() {
    return _variableId;
  }

  @JsonProperty("children")
  @Nonnull
  public ImmutableList<BooleanGuardAst> getChildren() {
    return _children;
  }

  /** Returns every referenced variable identity in deterministic order. */
  @JsonIgnore
  @Nonnull
  public ImmutableSet<String> getVariables() {
    Set<String> variables = new java.util.TreeSet<>();
    collectVariables(variables);
    return ImmutableSet.copyOf(variables);
  }

  private void collectVariables(Set<String> variables) {
    if (_variableId != null) {
      variables.add(_variableId);
    }
    _children.forEach(child -> child.collectVariables(variables));
  }

  /** Unambiguous representation used only for deterministic ordering and hashing. */
  @Nonnull
  public String canonicalForm() {
    if (_operator == Operator.VARIABLE) {
      return "V" + _variableId.length() + ":" + _variableId;
    }
    StringBuilder result = new StringBuilder(_operator.name()).append('(');
    _children.forEach(child -> result.append(child.canonicalForm()));
    return result.append(')').toString();
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj) {
      return true;
    }
    if (!(obj instanceof BooleanGuardAst)) {
      return false;
    }
    BooleanGuardAst other = (BooleanGuardAst) obj;
    return _operator == other._operator
        && Objects.equals(_variableId, other._variableId)
        && _children.equals(other._children);
  }

  @Override
  public int hashCode() {
    return Objects.hash(_operator, _variableId, _children);
  }
}
