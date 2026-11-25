"""Best-effort readable contracts, with unconditional equivalence certificates.

Reuse the established reference simplifier and normalization rules as candidate
generators. They never establish correctness by themselves. Keep free parameter
equalities explicitly, and accept a shorter candidate only after XOR is UNSAT.
"""
from region_smt import RegionFailure, ast, require_config_formula
from utils.util_norm import normalizer1, normalizer2
from utils.util_smt import serialize_smt2_sexpr as smt, subspec_string_to_smt2_and
from utils.util_symbolic import SmtSolver, SubspecificationError, and_expression, substitute_symbols


def simplify_allowed(runner, expression, names, *, composition=None):
    names = set(names)
    require_config_formula(expression, names)
    original = expression
    best = expression
    attempts = []

    def consider(method, candidate):
        nonlocal best
        require_config_formula(candidate, names)
        before, after = len(smt(best)), len(smt(candidate))
        if after >= before:
            return
        row = dict(method=method, before_bytes=before, candidate_bytes=after)
        try:
            row['equivalence'] = runner.check('readable_candidate_' + str(len(attempts)),
                                               ['xor', original, candidate])
        except RegionFailure as exc:
            row['equivalence'] = exc.status.value
        row['accepted'] = row['equivalence'] == 'unsat'
        attempts.append(row)
        if row['accepted']:
            best = candidate

    def try_method(method, operation):
        try:
            candidate = operation()
            if candidate is not None:
                consider(method, candidate)
        except (SubspecificationError, ValueError, TypeError) as exc:
            attempts.append(dict(method=method, accepted=False, error=str(exc)))

    # Recompose from the domain and the already normalized safety/support
    # predicates. This removes repeated Bad/Support scaffolding without
    # dropping the legal domain.
    if composition is not None:
        try_method('complete-domain-property-support', lambda: runner.simplify(
            'readable_composition', composition))
    try_method('existing-normalization-rules', lambda: ast(subspec_string_to_smt2_and(
        normalizer2(normalizer1(smt(best))))))

    if len(smt(best)) > 600:
        pins = tuple(pin for pin in runner.document.config_pins if pin.name in names)
        if {pin.name for pin in pins} == names:
            def reference():
                solver = SmtSolver(z3_path=runner.executable, timeout_seconds=min(runner.timeout, 5))
                text = solver.reference_simplify(runner.document, pins, best)
                return ast(subspec_string_to_smt2_and(text)) if text else None
            try_method('existing-protected-reference-simplifier', reference)

    # Infer constants through SMT implication, not by treating one satisfying
    # model as the entire solution set. Preserve every proved equality in the
    # output before substituting it into the residual formula.
    if names and best not in ('true', 'false'):
        def fixed_values():
            if runner.check('readable_satisfiable', best) == 'unsat':
                return 'false'
            values = runner.values('readable_model', best, sorted(names))
            fixed = {}
            for index, name in enumerate(sorted(names)):
                equality = ['=', name, values[name]]
                if runner.check(f'readable_fixed_{index:04d}',
                                and_expression([best, ['not', equality]])) == 'unsat':
                    fixed[name] = values[name]
            if not fixed:
                return None
            residual = runner.simplify('readable_fixed_residual', substitute_symbols(best, fixed))
            return runner.simplify('readable_fixed_reassemble', and_expression([
                *(['=', name, value] for name, value in fixed.items()), residual]))
        try_method('proved-fixed-values-with-explicit-bindings', fixed_values)

    # Applying the old final normalizer last preserves bvand instead of the
    # longer bvnot/bvor spelling that Z3 sometimes chooses on re-simplification.
    try_method('existing-final-normalizer', lambda: ast(subspec_string_to_smt2_and(normalizer2(smt(best)))))
    runner.prove('readable_final_equivalence', ['xor', original, best])
    return best, dict(method='certified-complete-allowed-simplification',
                      original_bytes=len(smt(original)), simplified_bytes=len(smt(best)),
                      equivalence='UNSAT', attempts=attempts)
