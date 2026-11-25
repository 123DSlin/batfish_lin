"""Run-local reuse with content-addressed proof provenance and no global cache."""
from hashlib import sha256
from solver_session import SolverSession
from utils.util_smt import serialize_smt2_sexpr as smt


class RegionContext:
    def __init__(self):
        self.session = SolverSession()
        self.native = None
        self.reference = {}
        self.policy_indexes = {}
        self.native_loads = 0
        self.reference_hits = 0
        self.reference_misses = 0
        self.policy_index_hits = 0
        self.summary_relations = None
        self.summary_evidence = None
        self.summary_hits = 0
        self.symbolic_reference = {}
        self.scope_relations = {}
        self.scope_reports = {}
        self.scope_hits = 0

    def close(self):
        self.session.close()

    def full_model(self, model, work):
        from property_regions import full_model
        # Inputs are private run-local copies. Still invalidate on replacement
        # or edits rather than reusing a parsed document from an earlier input.
        path = work / 'smt_encoding.smt2'
        stat = path.stat()
        signature = (id(model), str(work.resolve()), stat.st_ino, stat.st_size,
                     stat.st_mtime_ns, stat.st_ctime_ns)
        if self.native is not None and getattr(self, 'native_signature', None) == signature:
            return self.native
        source = (id(model), str(work.resolve()), sha256(path.read_bytes()).hexdigest())
        if self.native is None or self.native_source != source:
            self.native = full_model(model, work)
            self.native_source = source
            self.native_loads += 1
            self.summary_relations = None
            self.summary_evidence = None
            self.policy_indexes = {}
            self.scope_relations = {}
            self.scope_reports = {}
        self.native_signature = signature
        return self.native

    def device_relations(self, model, runner):
        if self.summary_relations is None:
            from device_summaries import build_summaries
            location = runner.output.parents[2] / 'device_summaries'
            self.summary_relations, self.summary_evidence = build_summaries(
                model, runner.executable, min(runner.timeout, 15), location, self.session)
            self.summary_report_path = str((location / 'device_summaries.json').resolve())
        else:
            self.summary_hits += 1
        return self.summary_relations

    def relation_scope(self, model, runner, name):
        if name in self.scope_relations:
            self.scope_hits += 1
            return self.scope_relations[name]
        from relational_scopes import build_scope
        if name == 'safety':
            roots = {model.property_symbol}
        else:
            roots = {symbol for symbol in model.document.declarations
                     if '_BGP_IMPORT_' in symbol
                     or symbol.startswith(('|0_CONTROL-', '|0_DATA-'))}
        location = runner.output.parents[2] / 'relational_scopes' / name
        relation, report = build_scope(model, roots, name, runner.executable,
                                       min(15, runner.timeout), location, self.session)
        self.scope_relations[name] = relation
        self.scope_reports[name] = {key: report[key] for key in (
            'method', 'eliminated_state_variables', 'native_variables', 'scope_variables')}
        self.scope_reports[name]['report'] = str((location/'scope_report.json').resolve())
        return relation

    def metrics(self):
        return dict(native_model_loads=self.native_loads, reference_cache_hits=self.reference_hits,
                    reference_checks=self.reference_misses, policy_index_builds=len(self.policy_indexes),
                    policy_index_hits=self.policy_index_hits, solver_process_starts=self.session.starts,
                    solver_session_queries=self.session.exchanges, device_summary_cache_hits=self.summary_hits,
                    device_summary_modules=(len(self.summary_evidence['modules']) if self.summary_evidence else 0),
                    summarized_devices=(sum(row['device'] != 'shared' and row['method'] == 'certified-existential-summary'
                                            for row in self.summary_evidence['modules']) if self.summary_evidence else 0),
                    eliminated_private_variables=(self.summary_evidence['eliminated_private_variables']
                                                  if self.summary_evidence else 0),
                    relational_scopes=self.scope_reports, relational_scope_cache_hits=self.scope_hits)

    def summary_provenance(self):
        return dict(report=self.summary_report_path,
                    eliminated_private_variables=self.summary_evidence['eliminated_private_variables'],
                    modules=[{key: row[key] for key in ('device', 'method', 'eliminated_private_variables')}
                             for row in self.summary_evidence['modules']])

    @staticmethod
    def normalize(expr):
        if not isinstance(expr, list):
            return expr
        items = [RegionContext.normalize(item) for item in expr]
        if items[0] == '=' and items[1] == items[2]:
            return 'true'
        if items[0] == 'and':
            items = ['and', *(item for item in items[1:] if item != 'true')]
            if len(items) == 1:
                return 'true'
            if len(items) == 2:
                return items[1]
        return items

    def reference_check(self, runner, label, expression):
        expression = self.normalize(expression)
        text = runner.document.query(f'(assert {smt(expression)})', '(check-sat)')
        key = sha256((str(runner.executable.resolve()) + '\n' + text).encode()).hexdigest()
        if key in self.reference:
            self.reference_hits += 1
            status, query = self.reference[key]
            return dict(status=status, cache_hit=True, source_query=query, sha256=key)
        self.reference_misses += 1
        status = runner.check(label, expression)
        query = str((runner.output / runner.queries[-1]['query']).resolve())
        self.reference[key] = status, query
        return dict(status=status, cache_hit=False, source_query=query, sha256=key)
