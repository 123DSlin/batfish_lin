"""Exact relational device summaries, retaining cross-device correlations.

Partitioning assigns each native assertion exactly once. Only variables private
within one partition are eliminated. No reference-route bindings are introduced.
"""
from collections import Counter
from pathlib import Path
import json

from candidate_recovery import definitions
from region_smt import QueryRunner, RegionFailure, Status
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import and_expression, collect_declared_symbols


def partition(document, routers, retained):
    routers = sorted(routers, key=len, reverse=True)

    def owner(name):
        for router in routers:
            if name.startswith((f'|0_{router}_', f'Config_{router}_')):
                return router
        return None

    pins = {pin.assertion_index for pin in document.config_pins}
    groups = {}
    for index, expr in enumerate(document.assertions):
        if index in pins:
            continue
        symbols = collect_declared_symbols(expr, document.declarations)
        writes = {owner(name) for name in definitions(expr, document.declarations)} - {None}
        reads = {owner(name) for name in symbols} - {None}
        owners = writes if len(writes) == 1 else reads
        label = next(iter(owners)) if len(owners) == 1 else 'shared'
        groups.setdefault(label, []).append(expr)
    variables = {label: collect_declared_symbols(and_expression(rows), document.declarations)
                 for label, rows in groups.items()}
    occurrences = Counter(name for names in variables.values() for name in names)
    boundary = set(retained) | {name for name, count in occurrences.items() if count > 1}
    return groups, variables, boundary


def build_summaries(model, executable, timeout, output, session):
    output = Path(output)
    runner = QueryRunner(model.document, executable, timeout, output, session=session)
    retained = ({name for name in model.document.declarations if name.startswith('Config_')}
                | set(model.failure_symbols.values()) | {model.property_symbol, '|0_dst-ip|'}
                | {name for name in model.document.declarations
                   if name.startswith(('|0_DATA-', '|0_CONTROL-'))})
    groups, variables, boundary = partition(model.document, model.forwarding, retained)
    summaries, details = [], []
    for index, (device, equations) in enumerate(sorted(groups.items())):
        body = and_expression(equations)
        targets = variables[device] & boundary
        private = variables[device] - boundary
        error = None
        if private:
            try:
                summary = runner.project(f'device_{index:04d}', body, targets)
                method = 'certified-existential-summary'
            except RegionFailure as exc:
                if exc.status not in (Status.INCOMPLETE,):
                    raise
                # Identity is an exact relation, not an over-approximation.
                # Uneliminated private variables remain in the later projection.
                summary, method, error = body, 'identity-relation', str(exc)
        else:
            summary, method = body, 'boundary-relation'
        summaries.append(summary)
        remaining = collect_declared_symbols(summary, model.document.declarations)
        details.append(dict(device=device, equations=len(equations), method=method, error=error,
                            variables_before=len(variables[device]), variables_after=len(remaining),
                            eliminated_private_variables=len(private - remaining),
                            relation=smt(summary)))
    result = dict(schema='exact-device-relations', modules=details,
                  original_assertions=sum(len(rows) for rows in groups.values()),
                  eliminated_private_variables=sum(row['eliminated_private_variables'] for row in details),
                  projection_certificates=runner.projection_certificates, metrics=runner.metrics())
    (output/'device_summaries.json').write_text(json.dumps(result, indent=2)+'\n')
    return summaries, result
