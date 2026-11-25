"""Certify every budgeted fault of a seed without expanding fault assignments."""
from pathlib import Path
import json

from region_smt import QueryRunner, RegionFailure, Status, ast
from solver_session import SolverSession
from utils.util_symbolic import SmtDocument, and_expression
from utils.util_smt import serialize_smt2_sexpr as smt


def check_seed(seed_text, guard_encoder, selection_guard, k, executable, timeout, output):
    document = SmtDocument.parse(seed_text)
    faults = {guard_encoder.symbol(variable.variable_id) for variable in guard_encoder.variables}
    if not faults <= document.declarations.keys():
        raise ValueError('seed is missing symbolic fault declarations')
    domain = and_expression([ast(guard_encoder.encode(selection_guard)),
                             ast(guard_encoder.at_most_k_expression(k))])
    session = SolverSession()
    runner = QueryRunner(document, Path(executable), timeout, Path(output), session=session)
    report = dict(strategy='symbolic', fault_assignments_enumerated=0,
                  fault_symbols=sorted(faults), domain=smt(domain), max_link_failures=k)
    try:
        if runner.check('guard_feasible', domain) != 'sat':
            report.update(status='ERROR', error='eligible branch has no budgeted fault assignment')
        else:
            existence = runner.project('seed_exists', and_expression(document.assertions), faults)
            missing = and_expression([domain, ['not', existence]])
            if runner.check('all_faults_covered', missing) == 'unsat':
                report.update(status='SAT', coverage_proof='UNSAT')
            else:
                values = runner.values('missing_fault_witness', missing, sorted(faults))
                failed = [variable.variable_id for variable in guard_encoder.variables
                          if values[guard_encoder.symbol(variable.variable_id)] ==
                          ('false' if variable.polarity == 'UP' else 'true')]
                report.update(status='UNSAT', coverage_proof='SAT', failed_variables=sorted(failed),
                              error='inconsistent failure assignment: ' + (', '.join(sorted(failed)) or 'none'))
    except RegionFailure as exc:
        status = ('TIMEOUT' if any(q['status'] == 'TIMEOUT' for q in runner.queries) else 'UNKNOWN')
        report.update(status=status if exc.status == Status.INCOMPLETE else 'ERROR', error=str(exc))
    finally:
        session.close()
    report['metrics'] = runner.metrics()
    report['solver_process_starts'] = session.starts
    (Path(output)/'coverage_report.json').write_text(json.dumps(report, indent=2)+'\n')
    return report
