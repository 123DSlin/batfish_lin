#!/usr/bin/env python3
"""Recompute source-level contracts from certified encoded line regions.

This is an exact deterministic inverse-image calculation, not a relabeling or
intersection of scalar field contracts. Historical result files stay intact.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from property_reports import write_subspecs
from speclens_granularity import command_plans, derive_contract
from solver_session import SolverSession
from utils.util_symbolic import SmtDocument, SubspecificationError


def adapt(source, configs, output, solver, timeout=60):
    source, configs, output = map(lambda value: Path(value).resolve(), (source, configs, output))
    if output.exists() or output.is_relative_to(source):
        raise SubspecificationError('output must be a new directory outside the source result')
    report_path = source / 'report.json'
    raw = json.loads(report_path.read_text())
    if raw['status'] != 'PASS' or raw.get('granularity') == 'speclens':
        raise SubspecificationError('requires a PASS result with encoded-variable line contracts')
    for name, digest in raw.get('input_sha256', {}).items():
        if sha256((source / 'input' / name).read_bytes()).hexdigest() != digest:
            raise SubspecificationError(f'input hash mismatch: {name}')
    for name, item in raw['line_level'].items():
        if item.get('status') != 'PASS' or not item.get('exact'):
            raise SubspecificationError(f'line lacks an exact PASS contract: {name}')
    # Validate all source mappings before creating any published outputs.
    plans = command_plans(raw['line_level'], configs)
    document = SmtDocument.parse((source / 'input/smt_encoding.smt2').read_text())
    output.mkdir(parents=True)
    shutil.copytree(source / 'input', output / 'input')
    snapshot = output / 'source_configs'
    snapshot.mkdir()
    for path in configs.iterdir():
        if path.is_file() and path.suffix.lower() in {'.cfg', '.conf'}:
            shutil.copyfile(path, snapshot / path.name)
    fields, lines = {}, {}
    session = SolverSession()
    try:
        for index, (name, plan) in enumerate(sorted(plans.items()), 1):
            encoded = raw['line_level'][name]
            directory = output / '3_property_subspecs' / f'line_{index:04d}'
            lines[name] = derive_contract(plan, encoded, document, solver, timeout,
                                          directory / 'line', session=session)
            lines[name]['evidence'] = str((directory / 'line').relative_to(output))
            lines[name]['encoded_line_evidence'] = str(source / encoded['evidence'])
            for number, field in enumerate(plan.fields, 1):
                location = directory / f'field_{number:04d}'
                item = derive_contract(plan, encoded, document, solver, timeout, location,
                                       field, session=session)
                item['evidence'] = str(location.relative_to(output))
                fields[field['id']] = item
            print(f'{index}/{len(plans)} {name}: {len(plan.fields)} source fields', flush=True)
    finally:
        session.close()
    report = {key: value for key, value in raw.items() if key not in {
        'field_level', 'line_level', 'execution_reuse', 'fixed_without_native_equations',
        'target_statuses', 'unsupported_config_fields'}}
    report.update(status='PASS', granularity='speclens',
                  target_scope='source-command-fields-with-encoded-effects',
                  field_level=fields, line_level=lines, source_fields=len(fields), source_lines=len(lines),
                  source=str(source), source_report_sha256=sha256(report_path.read_bytes()).hexdigest(),
                  method='certified-deterministic-pullback-of-exact-line-contracts',
                  source_mapping={name: plan.metadata() for name, plan in plans.items()},
                  source_limitations={name: plan.limitations for name, plan in plans.items() if plan.limitations},
                  errors={}, unsupported_config_fields=[],
                  scope='Source parameters represented by the export; command structure and existence remain fixed.')
    write_subspecs(output, fields, lines)
    text = json.dumps(report, indent=2) + '\n'
    (output / 'report.json').write_text(text)
    (output / '4_final_subspecs/final_subspecs.json').write_text(text)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--source-configs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--z3', default=shutil.which('z3'))
    parser.add_argument('--timeout', type=float, default=60)
    args = parser.parse_args()
    try:
        result = adapt(args.result, args.source_configs, args.output, args.z3, args.timeout)
    except (OSError, ValueError, SubspecificationError) as exc:
        print(f'Speclens adaptation failed: {exc}', file=sys.stderr)
        return 1
    print(f"PASS: {result['source_lines']} lines, {result['source_fields']} source fields")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
