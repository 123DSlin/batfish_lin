"""Discover prepend targets and write the standard field and line reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from utils.util_file import save_field_level_subspecs, save_line_level_subspecs
from utils.util_smt import parse_smt2_sexpr, tokenize_smt2_sexpr, serialize_smt2_sexpr as smt
from utils.util_symbolic import (
    ConfigPin,
    SubspecificationError,
    serialize_subspec_expression,
    substitute_symbols,
)

PREPEND_COST = "__prepend_aspath_cost"
PREPEND_ENABLE = "__prepend_aspath_enable"
PREPEND_FIELDS = {PREPEND_COST: "Int", PREPEND_ENABLE: "Bool"}


@dataclass(frozen=True)
class PrependLine:
    name: str
    owner: str
    fields: tuple[ConfigPin, ...]


def config_owner(name: str, routers) -> str:
    candidates = [router for router in routers if name.startswith(f"Config_{router}_")]
    if not candidates:
        raise SubspecificationError(f"no configuration owner for {name}")
    return max(candidates, key=len)


def prepend_lines(pins: tuple[ConfigPin, ...], routers) -> tuple[PrependLine, ...]:
    names = {pin.name: pin for pin in pins}
    groups = sorted({pin.name.removesuffix(suffix) for pin in pins for suffix in PREPEND_FIELDS
                     if pin.name.endswith(suffix)})
    result = []
    for group in groups:
        fields = []
        for suffix, sort in PREPEND_FIELDS.items():
            name = group + suffix
            if name not in names or names[name].sort != sort:
                raise SubspecificationError(f"incomplete prepend statement: {group}")
            fields.append(names[name])
        other = set(name for name in names if name.startswith(group + "__")) - {
            pin.name for pin in fields
        }
        if other:
            raise SubspecificationError(f"unsupported fields on prepend line {group}: {sorted(other)}")
        result.append(PrependLine(group, config_owner(group, routers), tuple(fields)))
    return tuple(result)


def write_subspecs(output: Path, fields: dict, lines: dict) -> None:
    final = output / "4_final_subspecs"
    final.mkdir(exist_ok=True)
    owners = sorted({item["owner"] for result in (fields, lines) for item in result.values()})
    source_mode = any(item.get('granularity') == 'speclens' for item in lines.values())
    for owner in (None, *owners):
        destination = final if owner is None else final / owner
        destination.mkdir(exist_ok=True)
        for filename, report, writer in (
            ("field_level_subspecs.txt", fields, save_field_level_subspecs),
            ("line_level_subspecs.txt", lines, save_line_level_subspecs),
        ):
            entries = {}
            raw_entries = {}
            for key, item in report.items():
                if owner is not None and item["owner"] != owner:
                    continue
                if source_mode and not item.get('source_fields'):
                    entries[key] = {'NOT_PARAMETERIZED (source arguments are not encoded; keep the original command)'}
                    raw_entries[key] = entries[key]
                    continue
                condition = item["allowed_constraint"]
                # Preserve the established output syntax, including 'empty'
                # for a Boolean field with no additional restriction.
                expression = parse_smt2_sexpr(tokenize_smt2_sexpr(condition))
                entries[key] = {"empty" if condition == "true"
                                else serialize_subspec_expression(expression)}
                raw_condition = item.get('raw_allowed_constraint', condition)
                raw_entries[key] = {'empty' if raw_condition == 'true' else serialize_subspec_expression(
                    parse_smt2_sexpr(tokenize_smt2_sexpr(raw_condition)))}
            writer(destination / filename, entries)
            if source_mode:
                writer(destination / filename.replace('.txt', '_raw.txt'), raw_entries)
        explained = [
            'Semantic subspecifications',
            'Field contracts hold with every other field at its original value.',
            'Line contracts allow joint changes within that line; other lines stay fixed.',
            'D is the legal configuration domain. Property and model-support conditions are relative to D.',
            'Allowed = D AND model-support condition AND property condition.',
            'A true property condition adds no safety restriction; it does not assign a configuration value.',
            '',
        ]
        if source_mode:
            explained[1:3] = [
                'Granularity: Speclens source commands and source fields; CIDR is one field.',
                'Field contracts fix other SOURCE fields; derived masks/endpoints are recompiled.',
                'Line contracts preserve command structure and jointly vary encoded source arguments.',
                'Line existence, list names and sequence numbers stay fixed; unsupported arguments are listed below.',
                'Text subspec files show the complete Allowed formula, including D; empty is used only when Allowed is true.',
                'Allowed is equivalence-certified and simplified before presentation; *_raw.txt and JSON retain the original formula.',
                'NOT_PARAMETERIZED means no source argument can be varied in this export; it is not an empty subspec.',
            ]
        for level, report in (('FIELD', fields), ('LINE', lines)):
            for name, item in sorted(report.items()):
                if owner is not None and item['owner'] != owner:
                    continue
                aliases = {name: 'h'} if level == 'FIELD' else {}
                if source_mode:
                    aliases = {}
                    for field in item.get('source_fields', []):
                        label = 'h' if level == 'FIELD' else field['label']
                        for index, symbol in enumerate(field['symbols']):
                            aliases[symbol] = label + ('.addr' if index == 0 else '.length') if field.get('kind') == 'IPv4-CIDR' else label

                def render(key):
                    value = item.get(key)
                    return smt(substitute_symbols(parse_smt2_sexpr(tokenize_smt2_sexpr(value)), aliases)) if value else 'not recorded in legacy report'

                explained.extend([f'{level}: {name}',
                                  f"  Domain metadata: {item.get('target_domains', {})}",
                                  f"  Legal domain D: {render('domain_constraint')}",
                                  f"  Property condition: {render('property_condition')}",
                                  f"  Model-support condition: {render('model_support_condition')}",
                                  f"  Allowed: {render('allowed_constraint')}", ''])
                if source_mode:
                    source = item['source']
                    explained[-1:-1] = [f"  Source: {source['file']}:{source['line']}",
                                        f"  Command: {source['command']}",
                                        f"  Edit status: {item.get('edit_status', 'PARAMETERIZED' if item.get('source_fields') else 'NOT_PARAMETERIZED')}",
                                        f"  Fields: {item.get('source_fields', [])}",
                                        f"  Limitations: {item.get('limitations', [])}"]
                if item.get('domain_reason') == 'original-value-only-without-native-equations':
                    explained.insert(len(explained) - 1, '  Model limitation: field effect is not encoded; only the original value is supported.')
        (destination / 'semantic_subspecs.txt').write_text('\n'.join(explained))
