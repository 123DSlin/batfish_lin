"""Certify encoded IMPORT/EXPORT policy changes and their downstream effects.

This checks the encoded transfer and its source records, not real-protocol
completeness. An activation must require a certified transfer's changed behavior.
"""
from utils.util_smt import expand_let_ast
from utils.util_symbolic import SmtDocument, and_expression, collect_declared_symbols, substitute_symbols
from region_smt import RegionFailure, Status


def definitions(expression, declared):
    """Collect oriented output equalities, excluding tests and implication guards."""
    result = {}

    def visit(expr):
        if isinstance(expr, str):
            if declared.get(expr) == 'Bool':
                result.setdefault(expr, set())
            return
        if not isinstance(expr, list) or not expr:
            return
        op = expr[0]
        if op == '=' and isinstance(expr[1], str) and expr[1] in declared:
            result.setdefault(expr[1], set()).update(collect_declared_symbols(expr[2], declared))
        elif op == '=' and isinstance(expr[2], str) and expr[2] in declared:
            result.setdefault(expr[2], set()).update(collect_declared_symbols(expr[1], declared))
        elif op in ('and', 'or'):
            for item in expr[1:]:
                visit(item)
        elif op == 'ite':
            visit(expr[2])
            visit(expr[3])
        elif op == '=>':
            guard = expr[1]
            if not (isinstance(guard, list) and len(guard) == 2 and guard[0] == 'not'
                    and isinstance(guard[1], str) and guard[1].endswith('_permitted|')):
                visit(expr[2])
        elif op == 'not' and len(expr) == 2 and isinstance(expr[1], str):
            if declared.get(expr[1]) == 'Bool':
                result.setdefault(expr[1], set())
    visit(expression)
    return result


class PolicyRecovery:
    def __init__(self, document, runner):
        self.document, self.runner = document, runner
        self.expressions = [expand_let_ast(expr, {}) for expr in document.assertions]
        self.records = {name.removesuffix('permitted|'): sorted(
            field for field in document.declarations
            if field.startswith(name.removesuffix('permitted|')) and not field.endswith('_choice|'))
            for name in document.declarations
            if name.endswith('_permitted|') and any(marker in name for marker in (
                '_IMPORT_', '_EXPORT_', '_SINGLE-EXPORT_', '_BEST_'))}
        self.owner = {field: prefix for prefix, fields in self.records.items() for field in fields}
        self.outputs = {}
        for expr in self.expressions:
            for field, dependencies in definitions(expr, document.declarations).items():
                self.outputs.setdefault(field, set()).update(dependencies)
        # Expand functional SSA helpers before inspecting policy dependencies or
        # restoring old configuration in a transfer. Route records stay inputs.
        choices = {}
        for expr in self.expressions:
            if (isinstance(expr, list) and len(expr) == 3 and expr[0] == '='
                    and isinstance(expr[1], str) and expr[1] in document.declarations
                    and expr[1] not in self.owner and not expr[1].startswith('Config_')
                    and not expr[1].startswith(('|0_FAILED-', '|0_CONTROL-', '|0_DATA-', '|0__reachable'))):
                choices.setdefault(expr[1], []).append(expr[2])
        aliases = {name: values[0] for name, values in choices.items() if len(values) == 1}

        def expand(expr, active=frozenset()):
            if isinstance(expr, str):
                return expand(aliases[expr], active | {expr}) if expr in aliases and expr not in active else expr
            return [expand(item, active) for item in expr]

        self.transfers = {}
        for prefix, fields in self.records.items():
            if not any(marker in prefix for marker in ('_BGP_IMPORT_', '_BGP_EXPORT_', '_BGP_SINGLE-EXPORT_')):
                continue
            producers = [expr for expr in self.expressions if isinstance(expr, list) and expr[0] == 'ite'
                         and prefix + 'permitted|' in definitions(expr, document.declarations)]
            if len(producers) == 1:
                self.transfers[prefix] = expand(producers[0])

    def require(self, condition, reason):
        if not condition:
            raise RegionFailure(Status.UNSUPPORTED, 'policy recovery: ' + reason)

    def source_closure(self, prefix):
        visited, pending, origins = set(), list(self.records[prefix]), set()
        while pending:
            current = pending.pop()
            if current in visited:
                continue
            visited.add(current)
            self.require(current in self.outputs, f'incomplete source field {current}')
            dependencies = {symbol for symbol in self.outputs[current] if symbol in self.owner}
            record = self.owner[current]
            if '_CONNECTED_IMPORT_' in record:
                # A native local origin must have a packet relevance equation,
                # rather than only a declared permitted bit.
                producers = [expr for expr in self.expressions if isinstance(expr, list)
                             and expr[0] == 'ite' and record + 'permitted|' in definitions(
                                 expr, self.document.declarations)]
                self.require(any('|0_dst-ip|' in collect_declared_symbols(expr, self.document.declarations)
                                 for expr in producers), f'local origin has no packet equation: {record}')
                origins.add(record)
            pending.extend(dependencies - visited)
        self.require(origins, 'source closure has no encoded connected origin')
        return dict(records=sorted({self.owner[field] for field in visited}),
                    fields=sorted(visited), origins=sorted(origins))

    def certify_transfer(self, prefix, label):
        candidate = prefix + 'permitted|'
        fields = self.records.get(prefix, [])
        self.require(len(fields) > 1, f'candidate has no encoded attributes: {candidate}')
        transfer = self.transfers.get(prefix)
        self.require(transfer is not None, f'missing or ambiguous policy transfer: {candidate}')
        outputs = definitions(transfer, self.document.declarations)
        self.require(all(field in outputs for field in fields), f'incomplete policy attributes: {candidate}')
        closure = self.source_closure(prefix)
        # Prove the transfer alone determines every active output attribute.
        # Global BEST/forwarding constraints must not hide a missing field equation.
        copies = {field: f'|policy_recovery_{label}::{field.strip("|")}|'
                  for field in fields}
        self.require(not set(copies.values()) & self.runner.document.declarations.keys(),
                     'duplicate transfer namespace')
        doc = self.runner.document
        forms = [f'(declare-fun {copy} () {doc.declarations[field]})'
                 for field, copy in copies.items()]
        self.runner.document = SmtDocument.parse(doc.query(*forms))
        disagreement = ['or', *(['not', ['=', field, copies[field]]] for field in fields)]
        query = and_expression([transfer, substitute_symbols(transfer, copies),
                                candidate, copies[candidate], disagreement])
        self.require(self.runner.check(label + '_transfer_ambiguous', query) == 'unsat',
                     'active policy attributes are not determined by its transfer')
        return dict(record=prefix, attributes=fields, source_closure=closure, transfer_ambiguous='UNSAT')

    def certify_activations(self, activated_candidates, targets, original_values, base, fixed_context):
        """Use old-policy counterfactuals at current inputs, not old winners.

        Every field in the line remains in the domain and state. Only actual
        dependencies select a transfer; a domain-coupled field need not appear
        textually in each transfer. No configuration values are enumerated.
        """
        roots, effects = [], {}
        for index, (prefix, transfer) in enumerate(sorted(self.transfers.items())):
            used = collect_declared_symbols(transfer, self.document.declarations)
            dependencies = targets & used
            if not dependencies:
                continue
            label = f'policy_transfer_{index:04d}'
            # state() substitutes fixed configuration and packet destination.
            # Apply exactly that context to the counterfactual too; leaving
            # those declared symbols free would create spurious explanations.
            current_transfer = substitute_symbols(transfer, fixed_context)
            old_transfer = substitute_symbols(current_transfer, original_values)
            effect = ['not', old_transfer]
            if self.runner.check(label + '_changed', and_expression([base, effect])) == 'unsat':
                continue
            row = self.certify_transfer(prefix, label)
            row.update(target_dependencies=sorted(dependencies),
                       other_line_targets=sorted(targets - dependencies),
                       direction='IMPORT' if '_BGP_IMPORT_' in prefix else 'EXPORT')
            roots.append(row)
            effects[prefix] = effect
        self.require(roots, 'activation has no encoded IMPORT/EXPORT policy change')
        recoveries = []
        for candidate, activation, label in activated_candidates:
            prefix = candidate.removesuffix('permitted|')
            row = self.certify_transfer(prefix, label)
            used = collect_declared_symbols(self.transfers[prefix], self.document.declarations)
            sources = [p for p in self.records if ('_EXPORT_' in p or '_SINGLE-EXPORT_' in p)
                       and p + 'permitted|' in used]
            self.require(len(sources) == 1, f'IMPORT has no unique advertisement source: {candidate}')
            causes = [root['record'] for root in roots if root['record'] in row['source_closure']['records']]
            self.require(causes, 'activation has no certified policy change in its source closure')
            changed_policy = ['or', *(effects[cause] for cause in causes)]
            self.require(self.runner.check(label + '_without_policy_change', and_expression([
                activation, ['not', changed_policy]])) == 'unsat',
                'activation can occur without a certified policy change')
            row.update(candidate=candidate, source=sources[0], causes=causes, without_policy_change='UNSAT',
                       kind=('local-policy-recovery' if prefix in causes else
                             'export-policy-recovery' if sources[0] in causes else 'downstream-propagation'))
            recoveries.append(row)
        return roots, recoveries
