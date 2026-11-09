"""Conditional-value adaptation for reference-style seed simplification.

This builds a candidate view only. Inactive values use canonical witnesses;
acceptance always requires proof against the original, unmodified symbolic
problem. All policy/route constraints remain in the view and no F is expanded.
"""
from __future__ import annotations

from typing import Any
from utils.util_symbolic import SmtDocument, collect_declared_symbols, substitute_symbols


class ReferenceSeedAdaptationError(RuntimeError):
    pass


def _nodes(tree: object, limit: int = 250000) -> int:
    pending=[tree];count=0
    while pending:
        current=pending.pop();count+=1
        if count>limit: raise ReferenceSeedAdaptationError('conditional value expansion exceeds size limit')
        if isinstance(current,list):pending.extend(current)
    return count


def conditional_value_view(
    document: SmtDocument, ordinary: object, snapshots: tuple[object, ...],
) -> tuple[object, dict[str, Any]]:
    """Expose guarded route/policy attribute equalities to value propagation."""
    groups: dict[str,list[tuple[object,object]]] = {}
    def visit(tree: object, guard: object='true', boundary: bool=False) -> None:
        if not isinstance(tree,list) or not tree:return
        op=tree[0]
        if op=='and':
            for child in tree[1:]:visit(child,guard,boundary)
        elif op=='ite' and len(tree)==4:
            visit(tree[2],['and',guard,tree[1]],boundary)
            visit(tree[3],['and',guard,['not',tree[1]]],boundary)
        elif op=='=>' and len(tree)==3:
            visit(tree[2],['and',guard,tree[1]],boundary)
        elif op=='=' and len(tree)==3 and isinstance(tree[1],str):
            symbol,value=tree[1:]
            if symbol not in document.declarations or symbol.startswith('Config_'):return
            if not boundary and not any(part in symbol for part in ('_BGP_IMPORT_','_BGP_EXPORT_')):return
            if document.declarations[symbol]=='Bool':return
            if symbol in collect_declared_symbols(value,document.declarations):return
            groups.setdefault(symbol,[]).append((guard,value))
    for snapshot in snapshots:visit(snapshot,boundary=True)
    visit(ordinary)
    substitutions={}
    for symbol,parts in groups.items():
        sort=document.declarations[symbol]
        if sort=='Int':default: object='0'
        elif sort.startswith('(_ BitVec '):default=['_','bv0',sort.removeprefix('(_ BitVec ').removesuffix(')')]
        else:continue
        value=default
        for guard,term in reversed(parts):value=['ite',guard,term,value]
        if symbol not in collect_declared_symbols(value,document.declarations):substitutions[symbol]=value
    expanded: dict[str,object]={};pending=set();cyclic=set()
    def expand(symbol: str) -> object:
        if symbol in expanded:return expanded[symbol]
        if symbol in pending:raise ReferenceSeedAdaptationError('conditional value dependency cycle')
        pending.add(symbol)
        try:
            tree=substitutions[symbol]
            dependencies=collect_declared_symbols(tree,document.declarations)&set(substitutions)
            tree=substitute_symbols(tree,{name:expand(name) for name in sorted(dependencies)})
            _nodes(tree,10000)
            expanded[symbol]=tree
            return tree
        finally:pending.remove(symbol)
    for symbol in sorted(substitutions):
        try:expand(symbol)
        except ReferenceSeedAdaptationError:cyclic.add(symbol)
    view=substitute_symbols(ordinary,expanded)
    count=_nodes(view)
    return view,dict(substituted_value_count=len(expanded),guarded_equation_count=sum(len(parts) for parts in groups.values()),
                     skipped_dependency_count=len(cyclic),candidate_view_nodes=count,
                     inactive_value_policy='candidate witness only; original-problem equivalence required')
