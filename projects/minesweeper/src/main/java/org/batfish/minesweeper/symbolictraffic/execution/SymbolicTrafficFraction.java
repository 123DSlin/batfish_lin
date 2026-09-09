package org.batfish.minesweeper.symbolictraffic.execution;

import java.util.ArrayList;
import java.util.Collection;
import java.util.HashSet;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import org.batfish.minesweeper.symbolicroute.BooleanGuardAst;
import org.batfish.minesweeper.symbolicroute.RouteGuard;

/**
 * One cell of {@code M[l, S]}. Algorithm 1 adds cells; Algorithm 2 fills them with {@code ω · c_r}
 * (constants, Boolean guards, sums, products, and the ECMP/SR quotients).
 */
public class SymbolicTrafficFraction {

  private enum Kind {
    CONST,
    GUARD,
    PLUS,
    TIMES,
    DIV
  }

  private static final SymbolicTrafficFraction ZERO = new SymbolicTrafficFraction(0.0);
  private static final SymbolicTrafficFraction ONE = new SymbolicTrafficFraction(1.0);
  private static final int JSON_DAG_NODE_LIMIT = 2048;
  private static final double KREDUCE_EPS = 1e-9;
  private static final int KREDUCE_MAX_VARS = 62;

  private final Kind _kind;
  private final double _const;
  private final RouteGuard _guard;
  private final SymbolicTrafficFraction _left;
  private final SymbolicTrafficFraction _right;

  public SymbolicTrafficFraction(double value) {
    this(Kind.CONST, value, null, null, null);
  }

  private SymbolicTrafficFraction(
      Kind kind,
      double constant,
      RouteGuard guard,
      SymbolicTrafficFraction left,
      SymbolicTrafficFraction right) {
    _kind = kind;
    _const = constant;
    _guard = guard;
    _left = left;
    _right = right;
  }

  public static SymbolicTrafficFraction zero() {
    return ZERO;
  }

  public static SymbolicTrafficFraction one() {
    return ONE;
  }

  public static SymbolicTrafficFraction fromGuard(RouteGuard guard) {
    Boolean folded = foldConstantAst(simplifyAst(guard.getAst()));
    if (Boolean.FALSE.equals(folded)) {
      return zero();
    }
    if (Boolean.TRUE.equals(folded)) {
      return one();
    }
    return new SymbolicTrafficFraction(Kind.GUARD, 0.0, guard, null, null);
  }

  public SymbolicTrafficFraction plus(SymbolicTrafficFraction other) {
    if (isZero()) {
      return other;
    }
    if (other.isZero()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const + other._const);
    }
    return new SymbolicTrafficFraction(Kind.PLUS, 0.0, null, this, other);
  }

  public SymbolicTrafficFraction times(SymbolicTrafficFraction other) {
    if (isZero() || other.isZero()) {
      return zero();
    }
    if (isOne()) {
      return other;
    }
    if (other.isOne()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const * other._const);
    }
    return new SymbolicTrafficFraction(Kind.TIMES, 0.0, null, this, other);
  }

  public SymbolicTrafficFraction times(double scalar) {
    return times(new SymbolicTrafficFraction(scalar));
  }

  /**
   * Quotient used by {@code c_r} and {@code c_p}. If the denominator is the constant {@code 0}, or
   * evaluates to {@code 0} at an assignment, the result is {@code 0} (no selected ECMP/SR member).
   */
  public SymbolicTrafficFraction div(SymbolicTrafficFraction other) {
    if (isZero() || other.isZero()) {
      return zero();
    }
    if (other.isOne()) {
      return this;
    }
    if (_kind == Kind.CONST && other._kind == Kind.CONST) {
      return new SymbolicTrafficFraction(_const / other._const);
    }
    return new SymbolicTrafficFraction(Kind.DIV, 0.0, null, this, other);
  }

  public boolean isZero() {
    if (_kind == Kind.CONST) {
      return _const == 0.0;
    }
    return _kind == Kind.GUARD
        && Boolean.FALSE.equals(foldConstantAst(simplifyAst(_guard.getAst())));
  }

  public boolean isOne() {
    return _kind == Kind.CONST && _const == 1.0;
  }

  public double getValue() {
    if (_kind != Kind.CONST) {
      throw new IllegalStateException("value is symbolic");
    }
    return _const;
  }

  /** Evaluate the formula at a Boolean assignment of guard variable ids. */
  public double evaluate(Map<String, Boolean> assignment) {
    return evaluate(assignment, new IdentityHashMap<SymbolicTrafficFraction, Double>());
  }

  /** Evaluate with every referenced guard variable set to true (the no-failure assignment). */
  public double evaluateAllUp() {
    Map<String, Boolean> assignment = new LinkedHashMap<>();
    collectVariables(assignment, new IdentityHashMap<SymbolicTrafficFraction, Boolean>());
    for (String variable : assignment.keySet()) {
      assignment.put(variable, true);
    }
    return evaluate(assignment);
  }

  /**
   * Human-readable formula. Constants and single guards stay infix. After {@link #kReduce}, the
   * polynomial is a small tree and is printed like YU Figure 5 ({@code 1*x1 + 0.5*(not x2)}). Shared
   * hop-accumulation DAGs stay as node-id text so they are not unfolded.
   */
  public String toDisplayString(int maxNodes) {
    if (_kind == Kind.CONST || _kind == Kind.GUARD) {
      return toString();
    }
    List<Map<String, Object>> nodes = new ArrayList<>();
    collectDag(new IdentityHashMap<SymbolicTrafficFraction, Integer>(), nodes);
    if (nodes.size() > maxNodes) {
      return "dag(" + nodes.size() + " nodes)";
    }
    if (hasSharedSubexpression()) {
      return toDagText();
    }
    return toInfix();
  }

  /**
   * YU §5.2 {@code KREDUCE(F, k)}: a polynomial that agrees with this STF on every assignment with
   * at most {@code k} failed variables (value {@code false}). Other assignments may differ.
   *
   * <p>{@code k = 0} is the all-up constant. Variables not in {@code variables} are held at {@code
   * true}. The result is {@code Σ_{|S|≤k} α_S Π_{x∈S} (not x)} with Möbius coefficients on the
   * subset lattice, matching Figure 5's summed scenario terms.
   */
  public SymbolicTrafficFraction kReduce(int k, Collection<String> variables) {
    if (k < 0) {
      throw new IllegalArgumentException("k-failure bound cannot be negative");
    }
    if (_kind == Kind.CONST) {
      return this;
    }
    List<String> vars = uniqueSorted(variables);
    if (vars.size() > KREDUCE_MAX_VARS) {
      return this;
    }
    if (vars.isEmpty() || k == 0) {
      return constant(evaluateMask(0L, vars));
    }
    int n = vars.size();
    int maxSize = Math.min(k, n);
    List<Long> masks = new ArrayList<>();
    for (int size = 0; size <= maxSize; size++) {
      collectMasks(n, size, masks);
    }
    Map<Long, Double> alpha = new LinkedHashMap<>();
    for (long mask : masks) {
      double value = evaluateMask(mask, vars);
      double sum = 0.0;
      for (Map.Entry<Long, Double> previous : alpha.entrySet()) {
        if ((previous.getKey() & mask) == previous.getKey()) {
          sum += previous.getValue();
        }
      }
      double coeff = value - sum;
      if (Math.abs(coeff) > KREDUCE_EPS) {
        alpha.put(mask, coeff);
      }
    }
    return polynomial(alpha, vars);
  }

  private double evaluate(
      Map<String, Boolean> assignment, IdentityHashMap<SymbolicTrafficFraction, Double> memo) {
    Double cached = memo.get(this);
    if (cached != null) {
      return cached;
    }
    double value;
    switch (_kind) {
      case CONST:
        value = _const;
        break;
      case GUARD:
        value = evaluateAst(_guard.getAst(), assignment) ? 1.0 : 0.0;
        break;
      case PLUS:
        value = _left.evaluate(assignment, memo) + _right.evaluate(assignment, memo);
        break;
      case TIMES:
        value = _left.evaluate(assignment, memo) * _right.evaluate(assignment, memo);
        break;
      case DIV:
        double denominator = _right.evaluate(assignment, memo);
        value = denominator == 0.0 ? 0.0 : _left.evaluate(assignment, memo) / denominator;
        break;
      default:
        throw new IllegalStateException("unsupported traffic-fraction kind");
    }
    memo.put(this, value);
    return value;
  }

  private void collectVariables(
      Map<String, Boolean> variables, IdentityHashMap<SymbolicTrafficFraction, Boolean> seen) {
    if (seen.containsKey(this)) {
      return;
    }
    seen.put(this, Boolean.TRUE);
    if (_kind == Kind.GUARD) {
      for (String variable : _guard.getAst().getVariables()) {
        variables.put(variable, Boolean.TRUE);
      }
      return;
    }
    if (_left != null) {
      _left.collectVariables(variables, seen);
    }
    if (_right != null) {
      _right.collectVariables(variables, seen);
    }
  }

  /**
   * Drop {@code true}, absorb {@code false}, and fold complementary literals {@code x ∧ ¬x}. Does
   * not call Z3.
   */
  private static BooleanGuardAst simplifyAst(BooleanGuardAst ast) {
    switch (ast.getOperator()) {
      case TRUE:
      case FALSE:
      case VARIABLE:
        return ast;
      case NOT:
        BooleanGuardAst negated = simplifyAst(ast.getChildren().get(0));
        if (negated.getOperator() == BooleanGuardAst.Operator.TRUE) {
          return BooleanGuardAst.falseValue();
        }
        if (negated.getOperator() == BooleanGuardAst.Operator.FALSE) {
          return BooleanGuardAst.trueValue();
        }
        if (negated.getOperator() == BooleanGuardAst.Operator.NOT) {
          return negated.getChildren().get(0);
        }
        return BooleanGuardAst.not(negated);
      case AND:
        return simplifyAnd(ast.getChildren());
      case OR:
        return simplifyOr(ast.getChildren());
      default:
        return ast;
    }
  }

  private static BooleanGuardAst simplifyAnd(List<BooleanGuardAst> children) {
    List<BooleanGuardAst> kept = new ArrayList<>();
    Set<BooleanGuardAst> atoms = new HashSet<>();
    for (BooleanGuardAst child : children) {
      BooleanGuardAst simplified = simplifyAst(child);
      if (simplified.getOperator() == BooleanGuardAst.Operator.FALSE) {
        return BooleanGuardAst.falseValue();
      }
      if (simplified.getOperator() == BooleanGuardAst.Operator.TRUE) {
        continue;
      }
      List<BooleanGuardAst> flat =
          simplified.getOperator() == BooleanGuardAst.Operator.AND
              ? simplified.getChildren()
              : java.util.Collections.singletonList(simplified);
      for (BooleanGuardAst atom : flat) {
        if (contradictsAnd(atoms, atom)) {
          return BooleanGuardAst.falseValue();
        }
        atoms.add(atom);
        kept.add(atom);
      }
    }
    if (kept.isEmpty()) {
      return BooleanGuardAst.trueValue();
    }
    if (kept.size() == 1) {
      return kept.get(0);
    }
    return BooleanGuardAst.and(kept);
  }

  private static BooleanGuardAst simplifyOr(List<BooleanGuardAst> children) {
    List<BooleanGuardAst> kept = new ArrayList<>();
    Set<BooleanGuardAst> atoms = new HashSet<>();
    for (BooleanGuardAst child : children) {
      BooleanGuardAst simplified = simplifyAst(child);
      if (simplified.getOperator() == BooleanGuardAst.Operator.TRUE) {
        return BooleanGuardAst.trueValue();
      }
      if (simplified.getOperator() == BooleanGuardAst.Operator.FALSE) {
        continue;
      }
      List<BooleanGuardAst> flat =
          simplified.getOperator() == BooleanGuardAst.Operator.OR
              ? simplified.getChildren()
              : java.util.Collections.singletonList(simplified);
      for (BooleanGuardAst atom : flat) {
        if (tautologyOr(atoms, atom)) {
          return BooleanGuardAst.trueValue();
        }
        atoms.add(atom);
        kept.add(atom);
      }
    }
    if (kept.isEmpty()) {
      return BooleanGuardAst.falseValue();
    }
    if (kept.size() == 1) {
      return kept.get(0);
    }
    return BooleanGuardAst.or(kept);
  }

  private static boolean contradictsAnd(Set<BooleanGuardAst> atoms, BooleanGuardAst atom) {
    if (atom.getOperator() == BooleanGuardAst.Operator.NOT) {
      return atoms.contains(atom.getChildren().get(0));
    }
    return atoms.contains(BooleanGuardAst.not(atom));
  }

  private static boolean tautologyOr(Set<BooleanGuardAst> atoms, BooleanGuardAst atom) {
    return contradictsAnd(atoms, atom);
  }

  /**
   * Fold an AST that does not depend on variables. {@code true ∧ ¬true} becomes {@code 0}, matching
   * the paper's {@code s_r = 0} without calling Z3 {@code Expr.isFalse()}.
   */
  private static Boolean foldConstantAst(BooleanGuardAst ast) {
    switch (ast.getOperator()) {
      case TRUE:
        return true;
      case FALSE:
        return false;
      case VARIABLE:
        return null;
      case NOT:
        Boolean negated = foldConstantAst(ast.getChildren().get(0));
        return negated == null ? null : !negated;
      case AND:
        boolean andAllTrue = true;
        for (BooleanGuardAst child : ast.getChildren()) {
          Boolean value = foldConstantAst(child);
          if (value == null) {
            andAllTrue = false;
            continue;
          }
          if (!value) {
            return false;
          }
        }
        return andAllTrue ? true : null;
      case OR:
        boolean orAllFalse = true;
        for (BooleanGuardAst child : ast.getChildren()) {
          Boolean value = foldConstantAst(child);
          if (value == null) {
            orAllFalse = false;
            continue;
          }
          if (value) {
            return true;
          }
        }
        return orAllFalse ? false : null;
      default:
        return null;
    }
  }

  private static boolean evaluateAst(BooleanGuardAst ast, Map<String, Boolean> assignment) {
    Boolean folded = foldConstantAst(ast);
    if (folded != null) {
      return folded;
    }
    switch (ast.getOperator()) {
      case TRUE:
        return true;
      case FALSE:
        return false;
      case VARIABLE:
        Boolean value = assignment.get(ast.getVariableId());
        if (value == null) {
          throw new IllegalArgumentException("no assignment for " + ast.getVariableId());
        }
        return value;
      case NOT:
        return !evaluateAst(ast.getChildren().get(0), assignment);
      case AND:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (!evaluateAst(child, assignment)) {
            return false;
          }
        }
        return true;
      case OR:
        for (BooleanGuardAst child : ast.getChildren()) {
          if (evaluateAst(child, assignment)) {
            return true;
          }
        }
        return false;
      default:
        throw new IllegalArgumentException("unsupported guard operator");
    }
  }

  @Override
  public boolean equals(Object o) {
    if (this == o) {
      return true;
    }
    if (!(o instanceof SymbolicTrafficFraction)) {
      return false;
    }
    SymbolicTrafficFraction other = (SymbolicTrafficFraction) o;
    if (_kind != other._kind) {
      return false;
    }
    if (_kind == Kind.CONST) {
      return Double.compare(_const, other._const) == 0;
    }
    return false;
  }

  @Override
  public int hashCode() {
    if (_kind == Kind.CONST) {
      return Double.hashCode(_const);
    }
    return _kind.hashCode();
  }

  /**
   * JSON form of this cell. Constants and single guards stay scalars. Compound {@code +}/{@code
   * *}/{@code /} are a DAG ({@code root} + {@code nodes}), never an unfolded infix tree: hop
   * accumulation shares subexpressions, and unfolding them is exponential.
   */
  public Object toJsonValue() {
    List<Map<String, Object>> nodes = new ArrayList<>();
    int root = collectDag(new IdentityHashMap<SymbolicTrafficFraction, Integer>(), nodes);
    if (nodes.size() == 1) {
      Map<String, Object> only = nodes.get(0);
      if ("const".equals(only.get("op"))) {
        return only.get("value");
      }
      if ("guard".equals(only.get("op"))) {
        return only.get("formula");
      }
    }
    if (nodes.size() <= JSON_DAG_NODE_LIMIT && !hasSharedSubexpression()) {
      return toInfix();
    }
    Map<String, Object> out = new LinkedHashMap<>();
    out.put("root", root);
    if (nodes.size() > JSON_DAG_NODE_LIMIT) {
      out.put("nodeCount", nodes.size());
      out.put("omitted", true);
      return out;
    }
    out.put("nodes", nodes);
    return out;
  }

  @Override
  public String toString() {
    switch (_kind) {
      case CONST:
        return Double.toString(_const);
      case GUARD:
        return formatAst(_guard.getAst());
      case PLUS:
      case TIMES:
      case DIV:
        return toDagText();
      default:
        return _kind.name();
    }
  }

  private String toDagText() {
    List<Map<String, Object>> nodes = new ArrayList<>();
    int root = collectDag(new IdentityHashMap<SymbolicTrafficFraction, Integer>(), nodes);
    StringBuilder out = new StringBuilder();
    for (int i = 0; i < nodes.size(); i++) {
      if (i > 0) {
        out.append(';');
      }
      Map<String, Object> node = nodes.get(i);
      out.append('n').append(node.get("id")).append('=');
      String op = String.valueOf(node.get("op"));
      if ("const".equals(op)) {
        out.append(node.get("value"));
      } else if ("guard".equals(op)) {
        out.append(node.get("formula"));
      } else {
        out.append("(n")
            .append(node.get("left"))
            .append(op)
            .append('n')
            .append(node.get("right"))
            .append(')');
      }
    }
    return "n" + root + "{" + out + "}";
  }

  private int collectDag(
      IdentityHashMap<SymbolicTrafficFraction, Integer> ids, List<Map<String, Object>> nodes) {
    Integer existing = ids.get(this);
    if (existing != null) {
      return existing;
    }
    Integer leftId = _left == null ? null : _left.collectDag(ids, nodes);
    Integer rightId = _right == null ? null : _right.collectDag(ids, nodes);
    int id = nodes.size();
    ids.put(this, id);
    Map<String, Object> node = new LinkedHashMap<>();
    node.put("id", id);
    switch (_kind) {
      case CONST:
        node.put("op", "const");
        node.put("value", _const);
        break;
      case GUARD:
        node.put("op", "guard");
        node.put("formula", formatAst(_guard.getAst()));
        break;
      case PLUS:
        node.put("op", "+");
        node.put("left", leftId);
        node.put("right", rightId);
        break;
      case TIMES:
        node.put("op", "*");
        node.put("left", leftId);
        node.put("right", rightId);
        break;
      case DIV:
        node.put("op", "/");
        node.put("left", leftId);
        node.put("right", rightId);
        break;
      default:
        node.put("op", _kind.name());
        break;
    }
    nodes.add(node);
    return id;
  }

  /** Solver-independent formula text; never calls Z3 {@code Expr.toString()}. */
  private static String formatAst(BooleanGuardAst ast) {
    switch (ast.getOperator()) {
      case TRUE:
        return "1";
      case FALSE:
        return "0";
      case VARIABLE:
        return ast.getVariableId();
      case NOT:
        return "(not " + formatAst(ast.getChildren().get(0)) + ")";
      case AND:
      case OR:
        StringBuilder out = new StringBuilder("(");
        String op = ast.getOperator() == BooleanGuardAst.Operator.AND ? " and " : " or ";
        for (int i = 0; i < ast.getChildren().size(); i++) {
          if (i > 0) {
            out.append(op);
          }
          out.append(formatAst(ast.getChildren().get(i)));
        }
        return out.append(')').toString();
      default:
        return ast.getOperator().name();
    }
  }

  public static SymbolicTrafficFraction fromAst(BooleanGuardAst ast) {
    return fromGuard(new AstRouteGuard(ast));
  }

  private static SymbolicTrafficFraction constant(double value) {
    if (Math.abs(value) <= KREDUCE_EPS) {
      return zero();
    }
    if (Math.abs(value - 1.0) <= KREDUCE_EPS) {
      return one();
    }
    return new SymbolicTrafficFraction(value);
  }

  private static List<String> uniqueSorted(Collection<String> variables) {
    Set<String> ids = new TreeSet<>();
    if (variables != null) {
      for (String variable : variables) {
        if (variable != null && !variable.isEmpty()) {
          ids.add(variable);
        }
      }
    }
    return new ArrayList<>(ids);
  }

  private static void collectMasks(int n, int size, List<Long> masks) {
    if (size == 0) {
      masks.add(0L);
      return;
    }
    int[] index = new int[size];
    for (int i = 0; i < size; i++) {
      index[i] = i;
    }
    while (true) {
      long mask = 0L;
      for (int i = 0; i < size; i++) {
        mask |= 1L << index[i];
      }
      masks.add(mask);
      int t = size - 1;
      while (t >= 0 && index[t] == n - size + t) {
        t--;
      }
      if (t < 0) {
        return;
      }
      index[t]++;
      for (int j = t + 1; j < size; j++) {
        index[j] = index[j - 1] + 1;
      }
    }
  }

  private double evaluateMask(long mask, List<String> vars) {
    Map<String, Boolean> assignment = new LinkedHashMap<>();
    for (int i = 0; i < vars.size(); i++) {
      assignment.put(vars.get(i), (mask & (1L << i)) == 0L);
    }
    Map<String, Boolean> extra = new LinkedHashMap<>();
    collectVariables(extra, new IdentityHashMap<SymbolicTrafficFraction, Boolean>());
    for (String variable : extra.keySet()) {
      assignment.putIfAbsent(variable, Boolean.TRUE);
    }
    return evaluate(assignment);
  }

  private static SymbolicTrafficFraction polynomial(Map<Long, Double> alpha, List<String> vars) {
    if (alpha.isEmpty()) {
      return zero();
    }
    Double empty = alpha.get(0L);
    if (alpha.size() == 1 && empty != null) {
      return constant(empty);
    }
    if (alpha.size() == 1) {
      Map.Entry<Long, Double> only = alpha.entrySet().iterator().next();
      if (Long.bitCount(only.getKey()) == 1 && Math.abs(only.getValue() - 1.0) <= KREDUCE_EPS) {
        return fromAst(BooleanGuardAst.not(BooleanGuardAst.variable(vars.get(bitIndex(only.getKey())))));
      }
    }
    if (alpha.size() == 2 && empty != null && Math.abs(empty - 1.0) <= KREDUCE_EPS) {
      for (Map.Entry<Long, Double> entry : alpha.entrySet()) {
        if (entry.getKey() != 0L
            && Long.bitCount(entry.getKey()) == 1
            && Math.abs(entry.getValue() + 1.0) <= KREDUCE_EPS) {
          return fromAst(BooleanGuardAst.variable(vars.get(bitIndex(entry.getKey()))));
        }
      }
    }
    SymbolicTrafficFraction result = zero();
    for (Map.Entry<Long, Double> entry : alpha.entrySet()) {
      SymbolicTrafficFraction term = constant(entry.getValue());
      long mask = entry.getKey();
      for (int i = 0; i < vars.size(); i++) {
        if ((mask & (1L << i)) != 0L) {
          term =
              term.times(fromAst(BooleanGuardAst.not(BooleanGuardAst.variable(vars.get(i)))));
        }
      }
      result = result.plus(term);
    }
    return result;
  }

  private static int bitIndex(long mask) {
    return Long.numberOfTrailingZeros(mask);
  }

  private boolean hasSharedSubexpression() {
    IdentityHashMap<SymbolicTrafficFraction, Integer> childRefs = new IdentityHashMap<>();
    IdentityHashMap<SymbolicTrafficFraction, Boolean> seen = new IdentityHashMap<>();
    countChildRefs(childRefs, seen);
    for (int count : childRefs.values()) {
      if (count > 1) {
        return true;
      }
    }
    return false;
  }

  private void countChildRefs(
      IdentityHashMap<SymbolicTrafficFraction, Integer> childRefs,
      IdentityHashMap<SymbolicTrafficFraction, Boolean> seen) {
    if (seen.containsKey(this)) {
      return;
    }
    seen.put(this, Boolean.TRUE);
    if (_left != null) {
      Integer previous = childRefs.get(_left);
      childRefs.put(_left, previous == null ? 1 : previous + 1);
      _left.countChildRefs(childRefs, seen);
    }
    if (_right != null) {
      Integer previous = childRefs.get(_right);
      childRefs.put(_right, previous == null ? 1 : previous + 1);
      _right.countChildRefs(childRefs, seen);
    }
  }

  private String toInfix() {
    switch (_kind) {
      case CONST:
        return formatConst(_const);
      case GUARD:
        return formatAst(_guard.getAst());
      case PLUS:
        return "(" + _left.toInfix() + " + " + _right.toInfix() + ")";
      case TIMES:
        return "(" + _left.toInfix() + " * " + _right.toInfix() + ")";
      case DIV:
        return "(" + _left.toInfix() + " / " + _right.toInfix() + ")";
      default:
        return _kind.name();
    }
  }

  private static String formatConst(double value) {
    if (value == Math.rint(value) && !Double.isInfinite(value)) {
      return Long.toString(Math.round(value));
    }
    return Double.toString(value);
  }

  /** AST-only guard so {@link #kReduce} does not need a Z3 context. */
  private static final class AstRouteGuard implements RouteGuard {
    private final BooleanGuardAst _ast;

    private AstRouteGuard(BooleanGuardAst ast) {
      _ast = ast;
    }

    @Override
    public BooleanGuardAst getAst() {
      return _ast;
    }

    @Override
    public RouteGuard and(RouteGuard other) {
      return new AstRouteGuard(BooleanGuardAst.and(_ast, other.getAst()));
    }

    @Override
    public RouteGuard or(RouteGuard other) {
      return new AstRouteGuard(BooleanGuardAst.or(_ast, other.getAst()));
    }

    @Override
    public RouteGuard not() {
      return new AstRouteGuard(BooleanGuardAst.not(_ast));
    }

    @Override
    public RouteGuard simplify() {
      return this;
    }

    @Override
    public boolean isSatisfiable() {
      return !isFalse();
    }

    @Override
    public boolean isEquivalentTo(RouteGuard other) {
      return _ast.equals(other.getAst());
    }

    @Override
    public boolean isTrue() {
      return Boolean.TRUE.equals(foldConstantAst(simplifyAst(_ast)));
    }

    @Override
    public boolean isFalse() {
      return Boolean.FALSE.equals(foldConstantAst(simplifyAst(_ast)));
    }
  }
}
