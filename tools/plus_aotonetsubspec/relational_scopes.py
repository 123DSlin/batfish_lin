"""Certified state-component scopes; discarded state retains its existence frontier.

Components are conditional on shared configuration/fault/packet inputs. A scope
keeps complete components, including competitors, and existentially eliminates
only other components. Input restrictions from eliminated components survive.
"""
from collections import defaultdict
from pathlib import Path
import json

from region_smt import QueryRunner, RegionFailure, Status
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import and_expression, collect_declared_symbols


def scope_components(document, inputs, roots):
    pins = {pin.assertion_index for pin in document.config_pins}
    rows = [expr for index, expr in enumerate(document.assertions) if index not in pins]
    dependencies = [collect_declared_symbols(row, document.declarations) for row in rows]
    adjacency = defaultdict(set)
    for index, symbols in enumerate(dependencies):
        for name in symbols - inputs:
            adjacency[name].add(index)
    pending, selected, retained = list(roots - inputs), set(), set(inputs)
    while pending:
        name = pending.pop()
        if name in retained:
            continue
        retained.add(name)
        for index in adjacency[name]:
            if index not in selected:
                selected.add(index)
                pending.extend(dependencies[index] - retained)
    # Inputs never propagate the dependency walk. Their constraints are not
    # dropped: exact projection produces the omitted components' frontier.
    return rows, retained, selected


def build_scope(model, roots, label, executable, timeout, output, session):
    document = model.document
    inputs = {name for name in document.declarations if name.startswith(('Config_', '|0_FAILED-'))}
    inputs.add('|0_dst-ip|')
    inputs &= document.declarations.keys()
    rows, retained, selected = scope_components(document, inputs, set(roots))
    source = and_expression(rows)
    all_symbols = collect_declared_symbols(source, document.declarations)
    removed = all_symbols - retained
    runner = QueryRunner(document, executable, timeout, Path(output), session=session)
    error = None
    if removed:
        # Eliminate only the disconnected remainder, not the kept routing core.
        # Sending the whole core to QE defeats the structural factorization.
        kernel, input_constraints, remainder = [], [], []
        for index, row in enumerate(rows):
            symbols = collect_declared_symbols(row, document.declarations)
            if index in selected:
                kernel.append(row)
            elif symbols - inputs:
                remainder.append(row)
            else:
                input_constraints.append(row)
        remainder_body = and_expression(remainder)
        shared = (collect_declared_symbols(and_expression(kernel), document.declarations)
                  & collect_declared_symbols(remainder_body, document.declarations))
        if shared - inputs:
            raise RegionFailure(Status.ERROR, 'scope factorization has a hidden shared state variable')
        try:
            frontier = runner.project(label, remainder_body, inputs)
            relation = and_expression([*kernel, *input_constraints, frontier])
            method = 'certified-existential-frontier'
        except RegionFailure as exc:
            if exc.status != Status.INCOMPLETE:
                raise
            relation, method, error = source, 'identity-relation', str(exc)
    else:
        relation, method = source, 'identity-relation'
    after = collect_declared_symbols(relation, document.declarations)
    report = dict(scope=label, method=method, error=error, roots=sorted(roots),
                  native_variables=len(all_symbols), scope_variables=len(after),
                  eliminated_state_variables=len(all_symbols-after),
                  kept_component_assertions=len(selected), source_assertions=len(rows),
                  factorization_proof='disjoint-hidden-state',
                  relation=smt(relation), projection_certificates=runner.projection_certificates,
                  metrics=runner.metrics())
    (Path(output)/'scope_report.json').write_text(json.dumps(report,indent=2)+'\n')
    return relation, report
