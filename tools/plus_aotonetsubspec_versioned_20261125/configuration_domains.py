"""Semantic configuration domains, represented as formulas rather than samples."""
from dataclasses import dataclass

from utils.util_symbolic import SubspecificationError, and_expression, substitute_symbols


@dataclass(frozen=True)
class IntegerDomain:
    minimum: int = 0
    maximum: int | None = None
    basis: str = 'nonnegative-integer'

    def expression(self, name):
        return and_expression([['<=', str(self.minimum), name], *(
            [['<=', name, str(self.maximum)]] if self.maximum is not None else [])])

    def metadata(self):
        return dict(kind='integer-interval', minimum=self.minimum, maximum=self.maximum, basis=self.basis)

    def contains(self, value):
        try:
            number = int(value)
        except (TypeError, ValueError):
            return False
        return number >= self.minimum and (self.maximum is None or number <= self.maximum)


@dataclass(frozen=True)
class BitVectorDomain:
    width: int
    basis: str = 'full-bitvector'

    def expression(self, name):
        return 'true'

    def metadata(self):
        return dict(kind='bitvector', width=self.width, basis=self.basis)

    def contains(self, value):
        try:
            number = int(value[2:], 16 if value.startswith('#x') else 2)
        except (TypeError, ValueError, AttributeError):
            return False
        return 0 <= number < 1 << self.width


SYMBOLIC_DOMAINS = (IntegerDomain, BitVectorDomain)


class DomainTargets(list):
    """Targets plus cross-field grammar constraints for the entire statement."""
    def __init__(self, targets=(), constraint='true', support='true'):
        super().__init__(targets)
        self.constraint = constraint
        self.support = support

    def rebind(self, targets):
        return DomainTargets(targets, self.constraint, self.support)


def numeric_domain(pin, cost_range=None):
    if pin.sort == 'Bool':
        return (False, True)
    if pin.name.endswith('__prepend_aspath_cost') and pin.sort == 'Int':
        if cost_range is not None:
            low, high = cost_range
            if not 0 <= low <= high:
                raise SubspecificationError('invalid regression prepend interval')
            return range(low, high + 1)
        # This is the abstract policy's repetition count, not a fabricated
        # packet-size or vendor command-line maximum.
        return IntegerDomain(basis='abstract-AS-path-prepend-count')
    if pin.sort == 'Int' and any(marker in pin.name for marker in ('__set_metric_', '__set_localpreference_')):
        # RFC 4271 sections 5.1.4/5.1.5: four-octet unsigned attributes.
        return IntegerDomain(0, (1 << 32) - 1, 'BGP-unsigned-32-bit-attribute')
    raise SubspecificationError(f'no semantic domain for configuration field: {pin.name}')


def prefix_domains(pins):
    by_suffix = {pin.name.rsplit('__', 1)[-1]: pin for pin in pins}
    sorts = dict(action='Bool', enable='Bool', ip='(_ BitVec 32)', mask='(_ BitVec 32)',
                 length='Int', prefix_range_start='Int', prefix_range_end='Int')
    if len(pins) != len(sorts) or {suffix: pin.sort for suffix, pin in by_suffix.items()} != sorts:
        raise SubspecificationError('expected one fully encoded IPv4 prefix-list entry')
    names = {suffix: pin.name for suffix, pin in by_suffix.items()}
    length, lower, upper = (names[key] for key in ('length', 'prefix_range_start', 'prefix_range_end'))
    mask, address = names['mask'], names['ip']
    constraint = and_expression([
        ['<=', length, lower], ['<=', lower, upper],
        ['=', mask, ['bvshl', '#xffffffff', [['_', 'int2bv', '32'], ['-', '32', length]]]],
        ['=', ['bvand', address, mask], address],
    ])
    targets = []
    for pin in pins:
        suffix = pin.name.rsplit('__', 1)[-1]
        domain = ((False, True) if pin.sort == 'Bool' else
                  BitVectorDomain(32, 'IPv4-prefix-syntax') if suffix in ('ip', 'mask') else
                  IntegerDomain(0, 32, 'IPv4-prefix-length'))
        targets.append((pin, domain))
    return DomainTargets(targets, constraint)


def specialize_targets(targets, selected):
    selected = set(selected)
    fixed = {pin.name: pin.original_value for pin, _ in targets if pin.name not in selected}
    return DomainTargets([(pin, domain) for pin, domain in targets if pin.name in selected],
                         substitute_symbols(targets.constraint, fixed))
