#!/usr/bin/env python3
"""Audit symbolic seed subspecs against an exhaustive, concrete-F intersection.

Enumeration belongs only to this bounded regression oracle. Production stage 3
reads each symbolic seed once and never calls this module. A concrete problem
substitutes *all* exported link booleans and removes their declarations before
solving; there is no remaining universal failure quantifier. Route snapshots,
configuration domains and destination scope use the same documented adapter.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from importlib import import_module
import hashlib
import json
from pathlib import Path
import sys
import time

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from consistency.branch_loader import SymbolicRib
from consistency.guard_encoder import GuardEncoder
from utils.util_smt import parse_smt2_sexpr, tokenize_smt2_sexpr, subspec_string_to_smt2_and
from utils.util_symbolic import (
    SmtSolver, SubspecificationError, and_expression, residual_declared_symbols,
    substitute_symbols, serialize_subspec_expression,
)

stage3 = import_module("3_branch_simplifier")


def concrete_document(document, encoder, failed):
    replacements = {
        encoder.symbol(v.variable_id): (
            "true" if ((v.variable_id not in failed) if v.polarity == "UP"
                       else (v.variable_id in failed)) else "false"
        ) for v in encoder.variables
    }
    unknown = set(document.branch_conditions().failure_variables) - replacements.keys()
    if unknown:
        raise SubspecificationError(f"oracle cannot pin failure symbols: {sorted(unknown)}")
    forms = []
    for form in document.declaration_forms:
        tree = parse_smt2_sexpr(tokenize_smt2_sexpr(form))
        if tree[1] not in replacements:
            forms.append(form)
    result = replace(
        document,
        declarations={k: v for k, v in document.declarations.items() if k not in replacements},
        declaration_forms=tuple(forms),
        assertions=tuple(substitute_symbols(a, replacements) for a in document.assertions),
        # Definitions are part of the context, so pin their link references too.
        definition_forms=tuple(serialize_subspec_expression(substitute_symbols(
            parse_smt2_sexpr(tokenize_smt2_sexpr(f)), replacements
        )) for f in document.definition_forms),
    )
    if result.branch_conditions().failure_variables:
        raise SubspecificationError("oracle retained symbolic failures")
    return result


def check_branch(work, branch, rib, encoder, k, solver, levels):
    started = time.monotonic()
    seed = work / "2_consistency_check" / branch["seed_file"]
    seed_bytes = seed.read_bytes()
    if hashlib.sha256(seed_bytes).hexdigest() != branch["seed_sha256"]:
        raise SubspecificationError(f"seed changed: {seed}")
    document = stage3._SmtDocument.parse(seed_bytes.decode())
    entry = rib.entry_index[branch["candidate_id"]]
    failures = encoder.satisfying_failure_assignments(entry.selection_guard, k)
    if not failures:
        raise SubspecificationError("branch has no legal concrete F")
    concrete = [concrete_document(document, encoder, f) for f in failures]
    # Keep destination-prefix semantics identical on both sides. Eliminate
    # device state first; direct mixed BV forall/exists QE can time out even
    # for /24. This shares only the destination adapter, not F expansion or
    # field/line reuse with the production scheduler.
    destination_adapter = stage3.SymbolicSubspecifier(work)
    destination_adapter.solver = solver
    fields = dict(stage3._field_targets(document.config_pins))
    lines = dict(stage3._group_config_pins(document.config_pins))
    checks = []
    for level, records, targets in [("field", branch["fields"], fields), ("line", branch["lines"], lines)]:
        if level not in levels:
            continue
        key = "config" if level == "field" else "line_group"
        if len(records) != len(targets) or {r[key] for r in records} != set(targets):
            raise SubspecificationError(f"incomplete {level} target coverage in stage 3")
        for record in records:
            name = record["config"] if level == "field" else record["line_group"]
            pins = targets[name]
            per_f = []
            formulas = []
            for failed, current in zip(failures, concrete):
                problem = current.quantified_projection(pins, branch["destination"])
                if set(problem.universal_names) - {problem.destination_symbol}:
                    raise SubspecificationError("concrete projection still quantifies failures")
                constraint = destination_adapter._staged_symbolic_projection(current, pins, problem)
                residual = residual_declared_symbols(constraint, current.declarations, problem.target_names)
                if residual:
                    raise SubspecificationError(f"concrete projection retained symbols: {residual}")
                formulas.append(parse_smt2_sexpr(tokenize_smt2_sexpr(
                    subspec_string_to_smt2_and(constraint) or "true"
                )))
                per_f.append({"failed": sorted(failed), "constraint": constraint})
            intersection = and_expression(formulas)
            equal, seconds = solver.equivalent(document, intersection, record["constraint"])
            checks.append({
                "level": level, "target": name, "symbolic_constraint": record["constraint"],
                "concrete_F_count": len(failures), "per_F": per_f,
                "enumerated_intersection": serialize_subspec_expression(intersection),
                "equivalence": "UNSAT" if equal else "NOT_PROVED",
                "equivalence_seconds": seconds,
            })
    return {
        "candidate_id": branch["candidate_id"], "branch": branch["branch_name"],
        "seed_sha256": branch["seed_sha256"], "concrete_F_count": len(failures),
        "status": "PASS" if all(c["equivalence"] == "UNSAT" for c in checks) else "FAIL",
        "seconds": time.monotonic() - started, "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--level", choices=["field", "line", "all"], default="all")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    work = args.work.resolve()
    source = work / "3_branch_subspecs" / "branch_subspecs.json"
    source_bytes = source.read_bytes()
    report = json.loads(source_bytes)
    if report["status"] != "PASS" or report["errors"]:
        raise SubspecificationError("a complete PASS stage 3 report is required")
    rib = SymbolicRib.from_work_directory(work)
    encoder = GuardEncoder(rib.guard_variables)
    solver = SmtSolver(timeout_seconds=args.timeout)
    levels = {"field", "line"} if args.level == "all" else {args.level}
    def run(branch):
        result = check_branch(work, branch, rib, encoder, report["scope"]["k"], solver, levels)
        print(f"{result['branch']}: {result['status']} ({len(result['checks'])} targets)", flush=True)
        return result
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, report["branches"]))
    payload = {
        "status": "PASS" if all(r["status"] == "PASS" for r in results) else "FAIL",
        "semantics": "symbolic-seed-subspec-equivalent-to-intersection-of-concrete-F-subspecs",
        "production_failure_enumeration": False, "oracle_failure_enumeration": True,
        "shared_model_adapters": ["route-snapshot-release", "destination-prefix-projection"],
        "source_report_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "target_checks": sum(len(r["checks"]) for r in results), "branches": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
