#!/usr/bin/env python3
"""Certify readable Allowed formulas in existing reports without network re-solving."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from contract_simplification import simplify_allowed
from property_reports import write_subspecs
from region_smt import QueryRunner, ast
from solver_session import SolverSession
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import SmtDocument, and_expression


def refresh(root, timeout=30):
    root = Path(root).resolve()
    report = json.loads((root / 'report.json').read_text())
    if report['status'] != 'PASS' or report.get('granularity') != 'speclens':
        raise ValueError('requires a PASS Speclens result')
    document = SmtDocument.parse((root / 'input/smt_encoding.smt2').read_text())
    changes = []
    session = SolverSession()
    try:
        for level in ('line_level', 'field_level'):
            for index, (name, item) in enumerate(sorted(report[level].items())):
                raw = item.get('raw_allowed_constraint', item['allowed_constraint'])
                location = root / 'readable_subspecs' / level / f'contract_{index:04d}'
                runner = QueryRunner(document, Path(shutil.which('z3')), timeout, location, session=session)
                expression, evidence = simplify_allowed(runner, ast(raw), set(item['target_domains']),
                    composition=and_expression([ast(item[key]) for key in (
                        'domain_constraint', 'property_condition', 'model_support_condition')]))
                item['raw_allowed_constraint'] = raw
                item['allowed_constraint'] = smt(expression)
                item['simplification'] = dict(evidence, evidence=str(location.relative_to(root)))
                changes.append(dict(level=level, target=name, **evidence))
    finally:
        session.close()
    # Publish only after every complete contract passed equivalence checking.
    serialized = json.dumps(report, indent=2) + '\n'
    (root / 'report.json').write_text(serialized)
    (root / '4_final_subspecs/final_subspecs.json').write_text(serialized)
    write_subspecs(root, report['field_level'], report['line_level'])
    summary = dict(status='PASS', contracts=len(changes),
                   shortened=sum(row['simplified_bytes'] < row['original_bytes'] for row in changes),
                   raw_bytes=sum(row['original_bytes'] for row in changes),
                   simplified_bytes=sum(row['simplified_bytes'] for row in changes), changes=changes)
    (root / 'readability_validation.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f"{root.name}: {summary['shortened']}/{summary['contracts']} shortened, "
          f"{summary['raw_bytes']} -> {summary['simplified_bytes']} bytes; all equivalent", flush=True)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('results', nargs='+', type=Path)
    parser.add_argument('--timeout', type=float, default=30)
    args = parser.parse_args()
    for path in args.results:
        refresh(path, args.timeout)
