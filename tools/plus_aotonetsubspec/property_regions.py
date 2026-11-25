"""Property-preserving regions over a fixed, explicitly declared configuration domain.

The production algorithm projects symbolic fault coverage, never configuration
values. Bad regions are exact existential projections at counterexample faults.
The candidate gate runs against the complete, unpruned model before projection.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import combinations
import math
from pathlib import Path
import re
import time

from property_model import PropertyModel
from candidate_recovery import PolicyRecovery
from configuration_domains import SYMBOLIC_DOMAINS, IntegerDomain, BitVectorDomain
from region_smt import QueryRunner, RegionFailure, Status, ast, require_config_formula
from utils.util_smt import serialize_smt2_sexpr as smt
from utils.util_symbolic import (
    ConfigPin, SmtDocument, and_expression, collect_declared_symbols, substitute_symbols,
)

Target = tuple[ConfigPin, Sequence]


def value_expression(value: object) -> object:
    if isinstance(value, bool):
        return "true" if value else "false"
    return ast(str(value))


def domain_expression(targets: Sequence[Target], assignments: Sequence[dict] | None = None) -> object:
    if not targets or len({pin.name for pin, _ in targets}) != len(targets):
        raise ValueError("region targets must be nonempty and unique")
    if assignments is not None:
        names = {pin.name for pin, _ in targets}
        if any(set(row) != names for row in assignments):
            raise ValueError("correlated domain rows must bind every target exactly once")
        return ["or", *(and_expression(["=", name, value_expression(value)]
                                      for name, value in row.items()) for row in assignments)]
    parts = [getattr(targets, 'constraint', 'true')]
    for pin, values in targets:
        if isinstance(values, SYMBOLIC_DOMAINS):
            parts.append(values.expression(pin.name))
            continue
        if not len(values):
            raise ValueError(f"empty target domain: {pin.name}")
        if isinstance(values, range) and values.step == 1:
            parts.extend([["<=", str(values.start), pin.name],
                          ["<=", pin.name, str(values.stop - 1)]])
        else:
            parts.append(["or", *(["=", pin.name, value_expression(value)] for value in values)])
    return and_expression(parts)


def domain_metadata(values: Sequence) -> dict | list:
    if isinstance(values, SYMBOLIC_DOMAINS):
        return values.metadata()
    if isinstance(values, range) and values.step == 1:
        return dict(kind="integer-interval", minimum=values.start, maximum=values.stop - 1)
    return list(values)


def domain_values(metadata: dict | list) -> Sequence:
    if isinstance(metadata, dict):
        if metadata.get('kind') == 'bitvector':
            return BitVectorDomain(metadata['width'], metadata.get('basis', 'full-bitvector'))
        if metadata.get("kind") != "integer-interval":
            raise ValueError("unknown symbolic domain representation")
        if metadata.get('maximum') is None or 'basis' in metadata:
            return IntegerDomain(metadata['minimum'], metadata.get('maximum'), metadata.get('basis', 'integer'))
        return range(metadata["minimum"], metadata["maximum"] + 1)
    return metadata


def domain_contains(metadata: dict | list, original: str) -> bool:
    """Membership without expanding an integer interval."""
    values = domain_values(metadata)
    if isinstance(values, SYMBOLIC_DOMAINS):
        return values.contains(original)
    if isinstance(values, range):
        try:
            return int(original) in values
        except ValueError:
            return False
    return any(smt(value_expression(value)) == original for value in values)


def full_model(model: PropertyModel, work: Path) -> PropertyModel:
    """Use native equations, removing only the exported counterexample request."""
    native = SmtDocument.parse((work / "smt_encoding.smt2").read_text())
    request = ["not", ["and", "true", model.property_symbol]]
    if native.assertions.count(request) != 1:
        raise RegionFailure(Status.UNSUPPORTED, "expected one native counterexample request")
    original_pins = {pin.name: pin for pin in native.config_pins}
    for pin in model.document.config_pins:
        original = original_pins.get(pin.name)
        if original is None or (original.sort, original.original_value) != (pin.sort, pin.original_value):
            raise RegionFailure(Status.UNSUPPORTED, f"native configuration differs: {pin.name}")
    document = SmtDocument.parse(native.query(
        *(f"(assert {smt(expr)})" for expr in native.assertions if expr != request)))
    return replace(model, document=document)


@dataclass
class RegionSolver:
    model: PropertyModel
    targets: Sequence[Target]
    k: int
    runner: QueryRunner
    max_failures: int = 10000
    max_regions: int = 1000
    assignments: Sequence[dict] | None = None
    bad_strategy: str = "cegar"
    context: object = None
    support_strategy: str = 'symbolic'

    def __post_init__(self) -> None:
        if self.k < 0 or self.max_failures <= 0 or self.max_regions <= 0:
            raise ValueError("invalid failure budget or region resource limit")
        if self.bad_strategy not in {"cegar", "direct"}:
            raise ValueError("unknown Bad projection strategy")
        if self.support_strategy not in ('symbolic', 'enumerate'):
            raise ValueError('unknown Support strategy')
        if self.model.document.definition_forms:
            raise RegionFailure(Status.UNSUPPORTED, "expanded native equations are required")
        self.names = {pin.name for pin, _ in self.targets}
        known = {pin.name: pin for pin in self.model.document.config_pins}
        if any(known.get(pin.name) != pin for pin, _ in self.targets):
            raise ValueError("target pins do not belong to this model")
        unpinned = {n for n in self.model.document.declarations if n.startswith("Config_")} - known.keys()
        if unpinned:
            raise RegionFailure(Status.UNSUPPORTED, f"configuration fields lack original pins: {sorted(unpinned)}")
        self.domain = domain_expression(self.targets, self.assignments)
        require_config_formula(self.domain, self.names)
        require_config_formula(getattr(self.targets, 'support', 'true'), self.names)
        self.failures = tuple(self.model.failure_symbols.values())
        if not self.failures or len(set(self.failures)) != len(self.failures):
            raise RegionFailure(Status.UNSUPPORTED, "missing or duplicate physical failure symbols")
        self.failure_count = sum(math.comb(len(self.failures), size)
                                 for size in range(min(self.k, len(self.failures)) + 1))
        if self.support_strategy == 'enumerate' and self.failure_count > self.max_failures:
            raise RegionFailure(Status.INCOMPLETE,
                                f"Support needs {self.failure_count} fault projections (limit {self.max_failures})")
        if self.support_strategy == 'symbolic' and self.max_failures < 2:
            raise RegionFailure(Status.INCOMPLETE, 'symbolic Support needs 2 fault projections')
        self.phase_seconds: dict[str, float] = {}
        self._base_states = {}
        self.summary_relations = None
        self.scope_relations = {}

    def scenarios(self):
        """Stream complete fault assignments; independent of configuration domain size."""
        for size in range(min(self.k, len(self.failures)) + 1):
            for failed in combinations(self.failures, size):
                yield {symbol: str(int(symbol in failed)) for symbol in self.failures}

    def state(self, failures: dict | None = None, *, reference: bool = False,
              summarized: bool = False, scope: str | None = None) -> object:
        key = (reference, summarized, scope)
        if key in self._base_states:
            base = self._base_states[key]
            return substitute_symbols(base, failures) if failures else base
        doc = self.model.document
        replacements = {pin.name: ast(pin.original_value) for pin in doc.config_pins
                        if reference or pin.name not in self.names}
        address = self.model.destination.split('/')[0]
        replacements['|0_dst-ip|'] = '#x' + ''.join(f'{int(part):02x}' for part in address.split('.'))
        pin_indices = {pin.assertion_index for pin in doc.config_pins}
        if scope in self.scope_relations:
            expressions = [self.scope_relations[scope]]
        elif summarized and self.summary_relations is not None:
            expressions = list(self.summary_relations)
        else:
            expressions = [expr for index, expr in enumerate(doc.assertions) if index not in pin_indices]
        expressions.append(getattr(self.targets, 'support', 'true'))
        expressions.extend(["or", ["=", name, "0"], ["=", name, "1"]] for name in self.failures)
        expressions.append(["<=", ["+", "0", *self.failures], str(self.k)])
        base = and_expression(substitute_symbols(expr, replacements) for expr in expressions)
        self._base_states[key] = base
        return substitute_symbols(base, failures) if failures else base

    def reference_support(self) -> None:
        if self.support_strategy == 'symbolic':
            self.reference_support_symbolic()
            return
        self.reference_support_evidence = []
        for index, failure in enumerate(self.scenarios()):
            label = f"reference_support_{index:04d}"
            expression = self.state(failure, reference=True)
            if self.context is None:
                result = dict(status=self.runner.check(label, expression), cache_hit=False)
            else:
                result = self.context.reference_check(self.runner, label, expression)
            self.reference_support_evidence.append(dict(failures=failure, **result))
            if result['status'] != "sat":
                raise RegionFailure(Status.UNSUPPORTED,
                                    f"reference model has no legal state at failure {index}; scope cannot be certified")

    def fault_domain(self):
        return and_expression([
            *(['or', ['=', name, '0'], ['=', name, '1']] for name in self.failures),
            ['<=', ['+', '0', *self.failures], str(self.k)]])

    def reference_support_symbolic(self):
        from hashlib import sha256
        source = self.state(reference=True, summarized=True)
        if self.context is not None:
            source = self.context.normalize(source)
        key = sha256(self.runner.document.query(f'(assert {smt(source)})').encode()).hexdigest()
        cache = self.context.symbolic_reference if self.context is not None else {}
        if key in cache:
            self.context.reference_hits += 1
            self.reference_support_evidence = [dict(cache[key], cache_hit=True)]
            return
        existence = self.runner.project('reference_exists', source, set(self.failures))
        if self.runner.check('reference_all_faults', and_expression([
                self.fault_domain(), ['not', existence]])) != 'unsat':
            raise RegionFailure(Status.UNSUPPORTED, 'reference model has no legal state for some budgeted fault')
        proof = dict(strategy='symbolic', status='SAT', coverage_proof='UNSAT', cache_hit=False,
                     legal_failures=self.failure_count, sha256=key, constraint=smt(existence),
                     source_query=str((self.runner.output / self.runner.queries[-1]['query']).resolve()))
        cache[key] = proof
        if self.context is not None:
            self.context.reference_misses += 1
        self.reference_support_evidence = [proof]

    def candidate_gate(self) -> None:
        self.candidate_scope = 'UNSAT'
        self.policy_recoveries = []
        self.policy_transfer_roots = []
        doc = self.model.document
        candidates = sorted(name for name, sort in doc.declarations.items()
                            if sort == "Bool" and re.fullmatch(r"\|0_[^|]+_BGP_IMPORT_[^|]+_permitted\|", name))
        if not candidates:
            raise RegionFailure(Status.UNSUPPORTED, "missing BGP IMPORT candidate inventory")
        old = self.state(reference=True, scope='candidate')
        internal = collect_declared_symbols(old, doc.declarations) - set(self.failures)
        renames = {name: f"|region_reference::{name.strip('|')}|" for name in internal}
        if set(renames.values()) & doc.declarations.keys():
            raise RegionFailure(Status.ERROR, "reference model namespace collision")
        if any(name not in renames for name in candidates):
            raise RegionFailure(Status.UNSUPPORTED, "candidate lacks reference-state equations")
        forms = [f"(declare-fun {new} () {doc.declarations[name]})" for name, new in sorted(renames.items())]
        # Only declarations are extended; none of the reference equations are
        # asserted globally or allowed to constrain later property projection.
        self.runner.document = SmtDocument.parse(doc.query(*forms))
        activation = ["or", *(["and", name, ["not", renames[name]]] for name in candidates)]
        query = and_expression([self.domain, self.state(scope='candidate'), substitute_symbols(old, renames), activation])
        status = self.runner.check("candidate_scope", query)
        if status == "sat":
            self.runner.values("candidate_scope_witness", query,
                               sorted(self.names) + list(self.failures) + candidates)
            coverage = PolicyRecovery(doc, self.runner, context=self.context)
            base = and_expression([self.domain, self.state(scope='candidate'), substitute_symbols(old, renames)])
            activated_candidates = []
            for index, candidate in enumerate(candidates):
                activated = and_expression([base, candidate, ['not', renames[candidate]]])
                label = f'policy_recovery_{index:04d}'
                if self.runner.check(label + '_activation', activated) == 'sat':
                    activated_candidates.append((candidate, activated, label))
            originals = {pin.name: ast(pin.original_value) for pin, _ in self.targets}
            fixed = {pin.name: ast(pin.original_value) for pin in doc.config_pins if pin.name not in self.names}
            address = self.model.destination.split('/')[0]
            fixed['|0_dst-ip|'] = '#x' + ''.join(f'{int(part):02x}' for part in address.split('.'))
            self.policy_transfer_roots, self.policy_recoveries = coverage.certify_activations(
                activated_candidates, self.names, originals, base, fixed)
            self.candidate_scope = 'CERTIFIED_POLICY_RECOVERY'

    def single_path_gate(self) -> None:
        multiple = []
        for router, peers in self.model.forwarding.items():
            ports = list(peers.values())
            discard = f"|0_CONTROL-FORWARDING_{router}_null_interface|"
            if discard in self.model.document.declarations:
                ports.append(discard)
            if len(ports) >= 2:
                multiple.append([">=", ["+", *(["ite", port, "1", "0"] for port in ports)], "2"])
        if multiple and self.runner.check("single_path_scope", and_expression([
                self.domain, self.state(scope='candidate'), ["or", *multiple]])) != "unsat":
            raise RegionFailure(Status.UNSUPPORTED, "target domain exceeds single-path forwarding scope")

    def bad_regions(self) -> tuple[object, list[dict]]:
        if self.bad_strategy == "direct":
            body = and_expression([self.domain, self.state(summarized=True), ["not", self.model.property_symbol]])
            bad = self.runner.project("bad_direct", body, self.names)
            return bad, [dict(strategy="direct", constraint=smt(bad))]
        bad: object = "false"
        regions = []
        visited = set()
        base = and_expression([self.domain, self.state(summarized=True), ["not", self.model.property_symbol]])
        while True:
            remaining = and_expression([base, ["not", bad]])
            if self.runner.check(f"bad_remaining_{len(regions):04d}", remaining) == "unsat":
                return bad, regions
            if len(regions) >= self.max_regions:
                raise RegionFailure(Status.INCOMPLETE, f"Bad projection exceeded {self.max_regions} regions")
            values = self.runner.values(f"bad_witness_{len(regions):04d}", remaining,
                                        list(self.failures) + sorted(self.names))
            failure = {name: values[name] for name in self.failures}
            if any(value not in {"0", "1"} for value in failure.values()):
                raise RegionFailure(Status.ERROR, "invalid physical failure witness")
            key = tuple(failure[name] for name in self.failures)
            if key in visited:
                raise RegionFailure(Status.INCOMPLETE, "a projected fault still has uncovered bad states")
            visited.add(key)
            body = and_expression([self.domain, self.state(failure, summarized=True), ["not", self.model.property_symbol]])
            region = self.runner.project(f"bad_project_{len(regions):04d}", body, self.names)
            point = substitute_symbols(region, {name: values[name] for name in self.names})
            self.runner.prove(f"bad_progress_{len(regions):04d}", ["not", point])
            regions.append(dict(failures=failure, configuration={name: values[name] for name in self.names},
                                constraint=smt(region)))
            bad = self.runner.simplify("bad_union", ["or", bad, region])
            require_config_formula(bad, self.names)

    def support_region(self) -> tuple[object, list[dict]]:
        if self.support_strategy == 'symbolic':
            joint = self.runner.project('support_joint_exists', and_expression([
                self.domain, self.state(summarized=True)]), self.names | set(self.failures))
            unsupported = self.runner.project('support_missing_fault', and_expression([
                self.domain, self.fault_domain(), ['not', joint]]), self.names)
            support = self.runner.simplify('support_symbolic', and_expression([
                self.domain, ['not', unsupported]]))
            return support, [dict(strategy='symbolic', failures=None, constraint=smt(joint),
                                  unsupported_constraint=smt(unsupported))]
        support: object = self.domain
        cases = []
        for index, failure in enumerate(self.scenarios()):
            body = and_expression([self.domain, self.state(failure, summarized=True)])
            projected = self.runner.project(f"support_project_{index:04d}", body, self.names)
            cases.append(dict(failures=failure, constraint=smt(projected)))
            support = self.runner.simplify("support_intersection", and_expression([support, projected]))
        require_config_formula(support, self.names)
        return support, cases

    def solve(self) -> dict:
        def phase(name, operation):
            start = time.monotonic()
            try:
                return operation()
            finally:
                self.phase_seconds[name] = time.monotonic() - start

        if self.context is not None:
            self.summary_relations = phase("device_summaries", lambda: self.context.device_relations(self.model, self.runner))
        phase("reference_support", self.reference_support)
        if self.context is not None:
            self.scope_relations = phase('relational_scopes', lambda: {
                name: self.context.relation_scope(self.model, self.runner, name)
                for name in ('candidate', 'safety')})
        phase("candidate_scope", self.candidate_gate)
        phase("single_path_scope", self.single_path_gate)
        bad, regions = phase("bad", self.bad_regions)
        support, cases = phase("support", self.support_region)
        allowed = self.runner.simplify("allowed_simplify", and_expression([self.domain, support, ["not", bad]]))
        property_condition = self.runner.within_domain('property_condition', ['not', bad], self.domain)
        model_support_condition = self.runner.within_domain('model_support_condition', support, self.domain)
        require_config_formula(allowed, self.names)
        start = time.monotonic()
        self.runner.prove("final_safety", and_expression([
            allowed, self.state(scope='safety'), ["not", self.model.property_symbol]]))
        self.runner.prove("final_domain", and_expression([allowed, ["not", self.domain]]))
        self.runner.prove("final_composition", ["xor", allowed,
                          and_expression([self.domain, support, ["not", bad]])])
        # Each Support body was independently compared to its quantified source.
        # Check that the published region entails every per-fault projection.
        for index, case in enumerate(cases):
            self.runner.prove(f"final_support_{index:04d}",
                              and_expression([allowed, self.fault_domain() if case.get('strategy') == 'symbolic' else 'true',
                                              ["not", ast(case["constraint"])]]))
        self.phase_seconds["certification"] = time.monotonic() - start
        result = dict(status=Status.PASS.value, exact=True, backend="regions", model_scope="full-native-equations",
                      semantics="all-legal-states-within-at-most-k", ingress=self.model.ingress,
                      metric_domains=dict(self.model.metric_domains),
                      encoding_semantics=dict(self.model.encoding_semantics),
                      destination=self.model.destination, property=self.model.property_symbol,
                      max_link_failures=self.k, legal_failures=self.failure_count,
                      target_domains={pin.name: domain_metadata(values) for pin, values in self.targets},
                      domain_constraint=smt(self.domain),
                      original_values={pin.name: pin.original_value for pin, _ in self.targets},
                      allowed_constraint=smt(allowed), bad_constraint=smt(bad), support_constraint=smt(support),
                      property_condition=smt(property_condition), model_support_condition=smt(model_support_condition),
                      condition_scope='relative-to-domain_constraint',
                      bad_regions=regions, support_cases=cases, candidate_scope=self.candidate_scope,
                      policy_recoveries=self.policy_recoveries,
                      policy_transfer_roots=self.policy_transfer_roots,
                      reference_support_evidence=self.reference_support_evidence,
                      device_summary_evidence=(self.context.summary_provenance() if self.context is not None else None),
                      projection_scope='exact-device-relations' if self.summary_relations is not None else 'native-equations',
                      relational_scope_evidence=(self.context.scope_reports if self.context is not None else None),
                      candidate_identity="directed-BGP-IMPORT-permitted-at-same-failure",
                      certification="model-relative; not an independent protocol proof",
                      configuration_values_enumerated=0,
                      projection_count=len(regions) + (2 if self.support_strategy == 'symbolic' else len(cases)),
                      support_strategy=self.support_strategy,
                      fault_assignments_enumerated=(0 if self.support_strategy == 'symbolic' else self.failure_count * 2),
                      bad_strategy=self.bad_strategy, output_bytes=len(smt(allowed).encode()),
                      phase_seconds=self.phase_seconds, metrics=self.runner.metrics())
        # Publish the allowed artifact only after every proof has succeeded.
        (self.runner.output / "allowed.smt2").write_text('\n'.join([
            *(f"(declare-fun {pin.name} () {pin.sort})" for pin, _ in self.targets),
            f"(assert {smt(allowed)})", "(check-sat)", ""]))
        return result
