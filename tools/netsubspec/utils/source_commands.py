"""Compile source-command locations for the stable-branch solver.

The parser/compiler follows the source-granularity adapter, independently of
Plus's property-preserving solver. CIDRs are compound fields; derived encoding
values and internal enable flags are not independently editable locations.
"""
from dataclasses import dataclass
from hashlib import sha256
import ipaddress
import json
from pathlib import Path
import re

from utils.util_symbolic import SubspecificationError, and_expression, substitute_symbols
from utils.util_smt import serialize_smt2_sexpr as smt, parse_smt2_sexpr, tokenize_smt2_sexpr


def ast(value):
    return parse_smt2_sexpr(tokenize_smt2_sexpr(value))


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
    return CommandPlan(line, command, original, compilation, fields, limitations)



def compile_document(document, group_pins, directory):
    """Substitute the deterministic command compiler before branch projection.

    Remove original bindings of derived values, rather than keeping their old
    values or existentially choosing them. All other seed assertions, including
    branch guards and state observations, remain in the same formula.
    """
    grouped = group_pins(document.config_pins)
    mapped = {p.name for _, pins in grouped for p in pins}
    missing = {p.name for p in document.config_pins} - mapped
    if missing:
        raise SubspecificationError('source command mapping missing for: ' + ', '.join(sorted(missing)))
    reports = {line: dict(original_values={p.name: p.original_value for p in pins})
               for line, pins in grouped}
    plans = command_plans(reports, directory) if reports else {}
    replacements, domains = {}, []
    for plan in plans.values():
        replacements.update({name: expr for name, expr in plan.compilation.items() if expr != name})
        syntax = plan.syntax_domain()
        domains.append(ast(syntax) if isinstance(syntax, str) else syntax)
        if plan.source.kind == 'prefix':
            names = {name.rsplit('__', 1)[-1]: name for name in plan.original}
            length, lower, upper = (names[k] for k in ('length', 'prefix_range_start', 'prefix_range_end'))
            mask, address = names['mask'], names['ip']
            domains.extend([['<=', '0', length], ['<=', length, '32'],
                            ['<=', length, lower], ['<=', lower, upper], ['<=', upper, '32'],
                            ['=', ['bvand', address, mask], address]])
    arguments = {name for plan in plans.values() for field in plan.fields for name in field['symbols']}
    for name in replacements:
        if name in arguments:
            raise SubspecificationError(f'derived value is also a source argument: {name}')
    omitted = {p.assertion_index for p in document.config_pins if p.name in replacements}
    forms = [f'(declare-fun {name} () {sort})' for name, sort in document.declarations.items()
             if name not in replacements]
    forms.extend(smt(substitute_symbols(ast(form), replacements)) for form in document.definition_forms)
    for index, (body, label) in enumerate(zip(document.assertions, document.assertion_names)):
        if index in omitted:
            continue
        body = substitute_symbols(body, replacements)
        if label is not None:
            body = ['!', body, ':named', label]
        forms.append(smt(['assert', body]))
    compiled = type(document).parse('\n'.join(forms))
    # Cached stage-local metadata; shared immutable seed data is never mutated.
    compiled.__dict__['source_plans'] = plans
    compiled.__dict__['source_domain'] = substitute_symbols(and_expression(domains), replacements)
    compiled.__dict__['source_compilation'] = {name: smt(expr) for name, expr in replacements.items()}
    return compiled


def source_targets(document, level):
    pins = {pin.name: pin for pin in document.config_pins}
    result = []
    for line, plan in sorted(document.source_plans.items()):
        if level == 'line':
            names = [name for field in plan.fields for name in field['symbols']]
            result.append((line, tuple(pins[name] for name in names)))
        else:
            for field in plan.fields:
                result.append((field['id'], tuple(pins[name] for name in field['symbols'])))
    return tuple(result)
