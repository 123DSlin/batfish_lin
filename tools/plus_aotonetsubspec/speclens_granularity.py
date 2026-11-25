"""Source-command locations and certified pullbacks of encoded line contracts.

A CIDR is one field. Masks and implicit range endpoints are compiled values,
not independently editable fields. Existing exact line regions can be reused:
the inverse image under a deterministic command compiler preserves their
all-states/all-faults quantifiers. No existential choice of another field is used.
"""
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
import re

from region_smt import QueryRunner, ast, require_config_formula
from utils.util_symbolic import SmtDocument, SubspecificationError, and_expression, substitute_symbols
from utils.util_smt import serialize_smt2_sexpr as smt


@dataclass
class SourceCommand:
    path: Path
    number: int
    text: str
    kind: str
    name: str
    sequence: int
    tokens: tuple

    def metadata(self):
        return dict(file=str(self.path.resolve()), line=self.number, command=self.text,
                    sha256=sha256(self.path.read_bytes()).hexdigest())


def read_commands(directory):
    """Read the supported Cisco source syntax; do not infer modifiers from SMT values."""
    directory = Path(directory)
    problem = directory.parent / 'problem.json'
    if problem.is_file():
        for filename, digest in json.loads(problem.read_text()).get('configuration_sha256', {}).items():
            path = directory / filename
            if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
                raise SubspecificationError(f'source configuration hash mismatch: {path}')
    devices = {}
    for path in sorted(directory.glob('*')):
        if not path.is_file() or path.suffix.lower() not in {'.cfg', '.conf'}:
            continue
        rows = path.read_text().splitlines()
        host = next((row.split()[1].lower() for row in rows if row.startswith('hostname ')), None)
        if host is None:
            continue
        if host in devices:
            raise SubspecificationError(f'duplicate source hostname: {host}')
        commands, policy, seq = [], None, 0
        for number, raw in enumerate(rows, 1):
            text, words = raw.strip(), raw.split()
            if not words:
                continue
            if words[0] == '!':
                policy = None
                continue
            if words[0] == 'route-map':
                policy, seq = words[1], int(words[3])
                continue
            if not raw[0].isspace():
                policy = None
            kind = name = None
            if words[:2] == ['ip', 'prefix-list']:
                if len(words) < 7 or words[3] != 'seq':
                    raise SubspecificationError(f'unsupported prefix-list syntax: {path}:{number}')
                kind, name, sequence = 'prefix', words[2], int(words[4])
            elif words[:3] == ['ip', 'community-list', 'standard']:
                kind, name, sequence = 'community-list', words[3], number
            elif policy is not None:
                sequence, name = seq, policy
                for start, candidate in ((['match', 'ip', 'address', 'prefix-list'], 'match-prefix'),
                                         (['match', 'community'], 'match-community'),
                                         (['set', 'as-path', 'prepend'], 'prepend'),
                                         (['set', 'metric'], 'metric'),
                                         (['set', 'local-preference'], 'local-preference'),
                                         (['set', 'community'], 'set-community')):
                    if words[:len(start)] == start:
                        kind = candidate
                        break
            if kind:
                commands.append(SourceCommand(path, number, text, kind, name, sequence, tuple(words)))
        devices[host] = commands
    if not devices:
        raise SubspecificationError(f'no hostname-bearing .cfg/.conf files in {directory}')
    return devices


def _format(text):
    # Matches the names in these native exports; reject ambiguous matches below.
    return re.sub(r'[^a-zA-Z0-9]', '_', text)


def _kind(line, values):
    if '_RouteFilterList_' in line:
        return 'prefix'
    if '_CommunityList_' in line:
        return 'community-list'
    names = ' '.join(values)
    for marker, kind in (('match_prefixlist_enable', 'match-prefix'),
                         ('match_community_list_enable', 'match-community'),
                         ('prepend_aspath_cost', 'prepend'), ('set_metric_', 'metric'),
                         ('set_localpreference_', 'local-preference'), ('set_community_', 'set-community')):
        if marker in names:
            return kind
    raise SubspecificationError(f'no source-command adapter for {line}')


def _number(value):
    if value.startswith('#x'):
        return int(value[2:], 16)
    if value.startswith('#b'):
        return int(value[2:], 2)
    return int(value)


@dataclass
class CommandPlan:
    line: str
    source: SourceCommand
    original: dict
    compilation: dict
    fields: list
    limitations: list

    def syntax_domain(self):
        # A preserved prepend command must contain at least one ASN. Zero
        # repetitions is an encoding no-op, not valid syntax for this command.
        return and_expression([['<=', '1', item['symbols'][0]] for item in self.fields
                               if item['label'] == 'prepend_count'])

    def replacements(self, field=None):
        free = {name for item in self.fields if field is None or item['id'] == field['id']
                for name in item['symbols']}
        fixed = {name: ast(value) for name, value in self.original.items() if name not in free}
        # Expand derived expressions with the same fixed source parameters.
        return {name: substitute_symbols(expr, fixed) for name, expr in self.compilation.items()}

    def metadata(self):
        return dict(source=self.source.metadata(), fields=self.fields, limitations=self.limitations,
                    compilation={name: smt(expr) for name, expr in self.compilation.items()})


def command_plans(line_reports, directory):
    devices = read_commands(directory)
    buckets = {}
    for line, report in sorted(line_reports.items()):
        owner = report.get('owner') or next((host for host in sorted(devices, key=len, reverse=True)
                                            if line.startswith(f'Config_{host}_')), None)
        if owner not in devices:
            raise SubspecificationError(f'missing source configuration for {line}')
        kind = _kind(line, report['original_values'])
        marker = '_RouteFilterList_' if kind == 'prefix' else '_CommunityList_' if kind == 'community-list' else '_RoutingPolicy_'
        name = line.split(marker, 1)[1].split('__', 1)[0]
        buckets.setdefault((owner, name, kind), []).append((line, report))
    plans = {}
    for (owner, name, kind), entries in buckets.items():
        candidates = sorted((item for item in devices[owner] if item.kind == kind and _format(item.name) == name),
                            key=lambda item: (item.sequence, item.number))
        if kind in {'prefix', 'community-list'}:
            for line, report in entries:
                index = int(re.search(r'__Line(\d+)$', line).group(1)) - 1
                if not 0 <= index < len(candidates):
                    raise SubspecificationError(f'no source entry for {line}')
                plans[line] = build_plan(line, report['original_values'], candidates[index])
        else:
            entries.sort(key=lambda item: tuple(map(int, re.search(r'__Seq(\d+)__Line(\d+)$', item[0]).groups())))
            # Some native policy sequence labels differ from CLI labels (X/FROM_T).
            # Match ordered statements within a named policy and command kind,
            # then validate the original arguments rather than trusting the labels.
            if len(entries) != len(candidates):
                raise SubspecificationError(f'ambiguous source mapping for {owner}/{name}/{kind}')
            for (line, report), command in zip(entries, candidates):
                plans[line] = build_plan(line, report['original_values'], command)
    return plans


def build_plan(line, original, command):
    compilation = {name: name for name in original}
    fields, limitations = [], []

    def add(label, symbols, value, **extra):
        fields.append(dict(id=line + '__' + label, label=label, symbols=list(symbols), original=value, **extra))

    def check(name, value):
        actual = original[name]
        same = actual == value if value in {'true', 'false'} else _number(actual) == _number(value)
        if not same:
            raise SubspecificationError(f'source/encoding value mismatch for {name}: {actual} != {value}')

    for name, value in original.items():
        if name.endswith('enable'):
            check(name, 'true')
            compilation[name] = 'true'
    if command.kind == 'prefix':
        names = {name.rsplit('__', 1)[-1]: name for name in original}
        if set(names) != {'ip', 'length', 'mask', 'prefix_range_start', 'prefix_range_end', 'action', 'enable'}:
            raise SubspecificationError(f'incomplete prefix entry: {line}')
        words = command.tokens
        network = ipaddress.IPv4Network(words[6], strict=True)
        modifiers = words[7:]
        if len(modifiers) % 2 or any(token not in {'ge', 'le'} for token in modifiers[::2]):
            raise SubspecificationError(f'unsupported prefix modifiers: {command.text}')
        bounds = dict(zip(modifiers[::2], map(int, modifiers[1::2])))
        if len(bounds) != len(modifiers) // 2:
            raise SubspecificationError(f'duplicate prefix modifiers: {command.text}')
        length, address = names['length'], names['ip']
        lower = bounds.get('ge', network.prefixlen)
        upper = bounds.get('le', 32 if 'ge' in bounds else network.prefixlen)
        expected = dict(ip=f'#x{int(network.network_address):08x}', length=str(network.prefixlen),
                        mask=f'#x{int(network.netmask):08x}', prefix_range_start=str(lower),
                        prefix_range_end=str(upper), action=str(words[5] == 'permit').lower())
        for suffix, value in expected.items():
            check(names[suffix], value)
        compilation[names['mask']] = ['bvshl', '#xffffffff', [['_', 'int2bv', '32'], ['-', '32', length]]]
        compilation[names['prefix_range_start']] = names['prefix_range_start'] if 'ge' in bounds else length
        compilation[names['prefix_range_end']] = names['prefix_range_end'] if 'le' in bounds else '32' if 'ge' in bounds else length
        add('action', [names['action']], words[5])
        add('prefix', [address, length], str(network), kind='IPv4-CIDR')
        for modifier, suffix in [('ge', 'prefix_range_start'), ('le', 'prefix_range_end')]:
            if modifier in bounds:
                add(modifier, [names[suffix]], bounds[modifier])
    else:
        for name, value in original.items():
            if name.endswith('enable'):
                continue
            if name.endswith('__action'):
                action = command.tokens[4]
                check(name, str(action == 'permit').lower())
                add('action', [name], action)
            elif name.endswith('__community'):
                encoded = re.search(r'(\d+)_(\d+)__community$', name)
                if not encoded or ':'.join(encoded.groups()) not in command.tokens:
                    raise SubspecificationError(f'source community mismatch: {name}')
                if command.kind == 'set-community' and len(command.tokens) != 3:
                    raise SubspecificationError(f'unsupported community set syntax: {command.text}')
                add('community', [name], ':'.join(encoded.groups()), scope='exported-standard-community-index')
            elif name.endswith('__prepend_aspath_cost'):
                asns = command.tokens[3:]
                if not asns or len(set(asns)) != 1 or not all(asn.isdigit() for asn in asns):
                    raise SubspecificationError(f'unsupported prepend syntax: {command.text}')
                check(name, str(len(asns)))
                add('prepend_count', [name], len(asns), repeated_asn=int(asns[0]))
                limitations.append('Only repetition count of the original ASN is encoded; ASN replacement is unsupported.')
            elif '__set_metric_' in name or '__set_localpreference_' in name:
                check(name, command.tokens[2])
                add('value', [name], int(command.tokens[2]))
            else:
                raise SubspecificationError(f'unmapped source field: {name}')
        if command.kind in {'match-prefix', 'match-community'}:
            limitations.append('Referenced list name is not symbolic in this export; this command has no encoded editable argument.')
    free = {name for field in fields for name in field['symbols']}
    for name, expr in compilation.items():
        require_config_formula(expr, free)
    return CommandPlan(line, command, original, compilation, fields, limitations)


def derive_contract(plan, encoded, document, solver, timeout, output, field=None, session=None):
    """Compute and certify a source-level line/field contract, not a scalar merge."""
    selected = [field] if field else plan.fields
    free = {name for item in selected for name in item['symbols']}
    replacements = plan.replacements(field)
    runner = QueryRunner(document, Path(solver), timeout, Path(output), session=session)
    formulas = {}
    for key in ('domain_constraint', 'bad_constraint', 'support_constraint', 'allowed_constraint',
                'property_condition', 'model_support_condition'):
        body = ast(encoded[key])
        if key in {'domain_constraint', 'allowed_constraint', 'support_constraint', 'bad_constraint'}:
            body = and_expression([body, plan.syntax_domain()])
        compiled = substitute_symbols(body, replacements)
        formulas[key] = runner.simplify('compile_' + key, compiled)
        require_config_formula(formulas[key], free)
        runner.prove('certify_' + key, ['xor', compiled, formulas[key]])
    for key in ('property_condition', 'model_support_condition'):
        normalized = runner.within_domain('source_' + key, formulas[key], formulas['domain_constraint'])
        runner.prove('relative_' + key, and_expression([
            formulas['domain_constraint'], ['xor', normalized, formulas[key]]]))
        formulas[key] = normalized
    from contract_simplification import simplify_allowed
    raw_allowed = smt(formulas['allowed_constraint'])
    formulas['allowed_constraint'], readability = simplify_allowed(
        runner, formulas['allowed_constraint'], free, composition=and_expression([
            formulas['domain_constraint'], formulas['property_condition'], formulas['model_support_condition']]))
    runner.prove('composition', ['xor', formulas['allowed_constraint'], and_expression([
        formulas['domain_constraint'], formulas['property_condition'], formulas['model_support_condition']])])
    originals = {name: ast(plan.original[name]) for name in free}
    if runner.check('original_domain', substitute_symbols(formulas['domain_constraint'], originals)) != 'sat':
        raise SubspecificationError(f'original command is outside its source domain: {plan.line}')
    # The compiler must reproduce every original encoded value, including all
    # derived bits and endpoints. This also checks source-to-encoding alignment.
    runner.prove('original_compilation', ['not', and_expression([
        ['=', substitute_symbols(expr, originals), ast(plan.original[name])]
        for name, expr in replacements.items()])])
    fixed_fields = {item['id']: item['original'] for item in plan.fields if item not in selected}
    result = dict(status='PASS', exact=True, backend='certified-command-pullback',
                  granularity='speclens', method='compile-source-field-into-exact-line-region',
                  raw_allowed_constraint=raw_allowed, simplification=readability,
                  condition_scope='relative-to-domain_constraint',
                  **{key: smt(value) for key, value in formulas.items()},
                  target_domains={name: encoded['target_domains'][name] for name in free},
                  original_values={name: plan.original[name] for name in free},
                  fixed_source_fields=fixed_fields, source=plan.source.metadata(),
                  source_fields=selected, limitations=plan.limitations,
                  edit_status='PARAMETERIZED' if free else 'NOT_PARAMETERIZED',
                  editable_source_arguments=bool(free),
                  compilation={name: smt(expr) for name, expr in replacements.items()},
                  owner=encoded['owner'], legal_failures=encoded.get('legal_failures'),
                  metrics=runner.metrics())
    if field:
        result.update(line=plan.line, field=field['label'], original_source_value=field['original'])
    return result
