#!/usr/bin/env python3
"""
Normalization Rules System

This module contains all normalization rules and the rule manager.
Rules can be used independently or as part of the subspec normalizer.

Author: Network Verification Team
Version: 2.0
"""

import re
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from abc import ABC, abstractmethod

from utils.util_smt import find_matching_paren, expand_let_expressions_ast, _unwrap_goal_content

# Configure logging
logger = logging.getLogger(__name__)


class NormalizationRule(ABC):
    """Abstract base class for all normalization rules
    
    This class provides a common interface for all normalization rules,
    making it easy to add new rules in the future.
    """
    
    def __init__(self, name: str, enabled: bool = True):
        """Initialize a normalization rule
        
        Args:
            name: Human-readable name of the rule
            enabled: Whether this rule is enabled (default: True)
        """
        self.name = name
        self.enabled = enabled
    
    @abstractmethod
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Apply this normalization rule to a subspec
        
        Args:
            subspec: The subspec string to normalize
            context: Optional context dictionary (e.g., containing helper methods)
            
        Returns:
            Normalized subspec string
        """
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', enabled={self.enabled})"


class LetExpressionExpansionRule(NormalizationRule):
    """Rule 1: Expand let expressions
    
    Expands all (let ((a!1 ...)) ...) expressions by replacing let-bound
    variables with their definitions.
    
    Features:
    - Self-contained implementation (no context dependency)
    - Reliable parsing using parenthesis matching (not string search)
    - Handles nested let expressions (from innermost to outermost)
    - Prevents variable capture using precise variable matching
    - Handles recursive let dependencies
    - Prevents exponential blow-up with size limits
    """
    
    def __init__(self, enabled: bool = True, max_expansion_size: int = 100000, max_iterations: int = 50):
        super().__init__("Let Expression Expansion", enabled=enabled)
        self.max_expansion_size = max_expansion_size  # Prevent exponential blow-up
        self.max_iterations = max_iterations  # Prevent infinite loops
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Expand all let expressions in the subspec using AST-based expansion.
        
        This uses efficient AST-based substitution instead of string-based replacement,
        avoiding O(N * #let) complexity.
        
        Args:
            subspec: The subspec string to expand (may contain " AND " separators)
            context: Optional context (not used, kept for compatibility)
            
        Returns:
            Expanded subspec with all let expressions replaced
        """
        if not self.enabled:
            return subspec
        
        # Handle subspecs that are joined with " AND " (common format)
        # Split by " AND ", expand each part separately, then rejoin
        if " AND " in subspec:
            parts = [part.strip() for part in subspec.split(" AND ") if part.strip()]
            if not parts:
                return subspec
            
            expanded_parts = []
            for part in parts:
                try:
                    expanded_part = expand_let_expressions_ast(part)
                    # Check size limit per part
                    if len(expanded_part) > self.max_expansion_size:
                        logger.warning(f"    [{self.name}] Part expansion would exceed size limit ({self.max_expansion_size}), using original")
                        expanded_parts.append(part)
                    else:
                        expanded_parts.append(expanded_part)
                except Exception as e:
                    # Log error and use original part if AST expansion fails
                    logger.error(f"    [{self.name}] AST expansion failed for part, using original: {e}")
                    expanded_parts.append(part)
            
            expanded = " AND ".join(expanded_parts)
            if expanded != subspec:
                logger.info(f"    [{self.name}] Expanded let expression(s) using AST-based substitution")
            return expanded
        
        # Single expression (no " AND " separator)
        try:
            expanded = expand_let_expressions_ast(subspec)
            
            # Check size limit to prevent exponential blow-up
            if len(expanded) > self.max_expansion_size:
                logger.warning(f"    [{self.name}] Expansion would exceed size limit ({self.max_expansion_size}), skipping")
                return subspec
            
            # Check if expansion actually changed anything
            if expanded != subspec:
                logger.info(f"    [{self.name}] Expanded let expression(s) using AST-based substitution")
            
            return expanded
        except Exception as e:
            # Log error and return original subspec if AST expansion fails
            logger.error(f"    [{self.name}] AST expansion failed, returning original subspec: {e}")
            return subspec
    
    def _apply_string_based(self, subspec: str) -> str:
        """Fallback string-based expansion method (kept for compatibility).
        
        This is the old implementation that uses string replacement.
        Only used if AST-based expansion fails.
        """
        # Use reliable detection: find all let expressions using parenthesis matching
        let_positions = self._find_all_let_expressions(subspec)
        if not let_positions:
            # Check for orphaned let-bound variables
            orphaned_vars = self._find_orphaned_let_vars(subspec)
            if orphaned_vars:
                logger.warning(f"    [{self.name}] Found orphaned let-bound variables: {orphaned_vars}")
            return subspec
        
        result = subspec
        iteration = 0
        total_expanded = 0
        
        # Expand from innermost to outermost (process in reverse order of positions)
        while iteration < self.max_iterations:
            let_positions = self._find_all_let_expressions(result)
            if not let_positions:
                break
            
            # Find the innermost let (highest start position)
            innermost = max(let_positions, key=lambda x: x[0])
            start_pos, end_pos = innermost
            
            # Extract and expand this let expression
            let_expr = result[start_pos:end_pos]
            expanded = self._expand_single_let(let_expr)
            
            if expanded == let_expr:
                # No change, might be malformed or already expanded
                logger.debug(f"    [{self.name}] No change after expansion attempt at position {start_pos}")
                break
            
            # Check size limit to prevent exponential blow-up
            if len(expanded) > self.max_expansion_size:
                logger.warning(f"    [{self.name}] Expansion would exceed size limit ({self.max_expansion_size}), skipping")
                break
            
            # Replace the let expression
            result = result[:start_pos] + expanded + result[end_pos:]
            total_expanded += 1
            iteration += 1
        
        if total_expanded > 0:
            logger.info(f"    [{self.name}] Expanded {total_expanded} let expression(s) in {iteration} iteration(s)")
        
        if iteration >= self.max_iterations:
            logger.warning(f"    [{self.name}] Reached max iterations ({self.max_iterations})")
        
        # Final check for orphaned variables
        orphaned_vars = self._find_orphaned_let_vars(result)
        if orphaned_vars:
            logger.warning(f"    [{self.name}] Remaining orphaned let-bound variables: {orphaned_vars}")
        
        return result
    
    def _find_all_let_expressions(self, expr: str) -> List[Tuple[int, int]]:
        """Find all let expressions using reliable parenthesis matching
        
        Returns:
            List of (start_pos, end_pos) tuples for each let expression
        """
        positions = []
        i = 0
        
        while i < len(expr):
            # Look for "(let" - but check it's a complete token
            if i + 4 <= len(expr) and expr[i:i+4] == "(let":
                # Check that it's not part of a longer identifier
                if (i == 0 or not (expr[i-1].isalnum() or expr[i-1] == '_' or expr[i-1] == '!')):
                    # Found potential let, parse it
                    let_start = i
                    let_end = find_matching_paren(expr, i)
                    
                    if let_end > 0:
                        positions.append((let_start, let_end + 1))
                        i = let_end + 1
                        continue
            
            i += 1
        
        return positions
    
    def _expand_single_let(self, let_expr: str) -> str:
        """Expand a single let expression
        
        Args:
            let_expr: A complete let expression like "(let ((a!1 expr1)) body)"
            
        Returns:
            Expanded expression with let-bound variables replaced
        """
        if not let_expr.startswith("(let"):
            return let_expr
        
        # Parse the let expression structure: (let ((var1 expr1) (var2 expr2) ...) body)
        i = 4  # Skip "(let"
        
        # Skip whitespace
        while i < len(let_expr) and let_expr[i].isspace():
            i += 1
        
        if i >= len(let_expr) or let_expr[i] != '(':
            return let_expr  # Malformed
        
        # Parse bindings block: ((var1 expr1) (var2 expr2) ...)
        bindings_start = i
        bindings_end = find_matching_paren(let_expr, i)
        if bindings_end < 0:
            return let_expr  # Malformed
        
        bindings_block = let_expr[bindings_start + 1:bindings_end]  # Remove outer parens
        
        # Parse body (everything after bindings)
        body_start = bindings_end + 1
        while body_start < len(let_expr) and let_expr[body_start].isspace():
            body_start += 1
        
        # Body is everything until the closing paren of the let expression
        body_end = len(let_expr) - 1  # Last char should be ')'
        body = let_expr[body_start:body_end].strip()
        
        # Extract bindings
        bindings = self._parse_bindings(bindings_block)
        if not bindings:
            return let_expr  # No bindings found
        
        # Resolve dependencies: if a binding references another binding, order matters
        ordered_bindings = self._resolve_binding_dependencies(bindings)
        
        # Replace variables in body, handling variable capture prevention
        expanded_body = self._replace_variables_safely(body, ordered_bindings)
        
        return expanded_body
    
    def _parse_bindings(self, bindings_block: str) -> List[Tuple[str, str]]:
        """Parse bindings from a bindings block
        
        Args:
            bindings_block: String like "(a!1 expr1) (a!2 expr2)"
            
        Returns:
            List of (variable_name, expression) tuples
        """
        bindings = []
        i = 0
        
        while i < len(bindings_block):
            # Skip whitespace
            while i < len(bindings_block) and bindings_block[i].isspace():
                i += 1
            
            if i >= len(bindings_block):
                break
            
            # Expect a binding: (var expr)
            if bindings_block[i] != '(':
                i += 1
                continue
            
            binding_start = i
            binding_end = find_matching_paren(bindings_block, i)
            if binding_end < 0:
                break
            
            binding_str = bindings_block[binding_start + 1:binding_end]  # Remove parens
            
            # Parse variable and expression
            parts = binding_str.strip().split(None, 1)  # Split on first whitespace
            if len(parts) == 2:
                var = parts[0].strip()
                expr = parts[1].strip()
                bindings.append((var, expr))
            
            i = binding_end + 1
        
        return bindings
    
    def _resolve_binding_dependencies(self, bindings: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Resolve dependencies between bindings
        
        If binding B references variable from binding A, A must be expanded before B.
        Uses topological sort to determine correct order.
        
        Args:
            bindings: List of (var, expr) tuples
            
        Returns:
            Ordered list of bindings with dependencies resolved
        """
        # Build dependency graph
        var_to_index = {var: i for i, (var, _) in enumerate(bindings)}
        dependencies = {i: set() for i in range(len(bindings))}
        
        for i, (var, expr) in enumerate(bindings):
            # Find which other variables this expression references
            for other_var, _ in bindings:
                if other_var != var and self._var_occurs_in(other_var, expr):
                    if other_var in var_to_index:
                        dependencies[i].add(var_to_index[other_var])
        
        # Topological sort
        ordered = []
        visited = set()
        temp_visited = set()
        
        def visit(node):
            if node in temp_visited:
                # Circular dependency detected
                return
            if node in visited:
                return
            
            temp_visited.add(node)
            for dep in dependencies[node]:
                visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            ordered.append(node)
        
        for i in range(len(bindings)):
            if i not in visited:
                visit(i)
        
        return [bindings[i] for i in ordered]
    
    def _var_occurs_in(self, var: str, expr: str) -> bool:
        """Check if a variable occurs in an expression (as a standalone token)
        
        Prevents false matches like "a!1" matching "a!10"
        """
        # Use word boundary matching
        pattern = rf'(?<![a-zA-Z0-9!_]){re.escape(var)}(?![a-zA-Z0-9!])'
        return bool(re.search(pattern, expr))
    
    def _replace_variables_safely(self, body: str, bindings: List[Tuple[str, str]]) -> str:
        """Replace variables in body with their expressions, preventing variable capture
        
        Args:
            body: The body expression
            bindings: Ordered list of (var, expr) tuples
            
        Returns:
            Body with variables replaced
        """
        result = body
        
        # Process bindings in reverse order (innermost first) to handle nested scopes correctly
        for var, expr in reversed(bindings):
            # Find all occurrences of var as a standalone token
            # Use word boundary matching to prevent partial matches
            pattern = rf'(?<![a-zA-Z0-9!_]){re.escape(var)}(?![a-zA-Z0-9!])'
            
            def replace_func(match):
                # Wrap expression in parentheses if it's complex
                if expr.startswith('(') or not any(op in expr for op in [' ', '(', ')']):
                    return expr
                else:
                    return f"({expr})"
            
            result = re.sub(pattern, replace_func, result)
        
        return result
    
    def _find_orphaned_let_vars(self, expr: str) -> List[str]:
        """Find let-bound variables that appear without a corresponding let expression
        
        Returns:
            List of orphaned variable names
        """
        # Pattern for let-bound variables: a!1, a!2, etc.
        pattern = r'\ba!\d+\b'
        matches = re.findall(pattern, expr)
        
        # Check if there are any let expressions
        let_positions = self._find_all_let_expressions(expr)
        if let_positions:
            # Extract all bound variables from let expressions
            bound_vars = set()
            for start, end in let_positions:
                let_expr = expr[start:end]
                bindings = self._parse_bindings_from_let(let_expr)
                bound_vars.update(var for var, _ in bindings)
            
            # Return only orphaned variables
            return [var for var in matches if var not in bound_vars]
        
        return matches
    
    def _parse_bindings_from_let(self, let_expr: str) -> List[Tuple[str, str]]:
        """Parse bindings from a complete let expression (helper for orphan detection)"""
        if not let_expr.startswith("(let"):
            return []
        
        i = 4  # Skip "(let"
        while i < len(let_expr) and let_expr[i].isspace():
            i += 1
        
        if i >= len(let_expr) or let_expr[i] != '(':
            return []
        
        bindings_end = find_matching_paren(let_expr, i)
        if bindings_end < 0:
            return []
        
        bindings_block = let_expr[i + 1:bindings_end]  # Remove outer parens
        return self._parse_bindings(bindings_block)


class BitwiseDeMorganRule(NormalizationRule):
    """Rule 3: Apply De Morgan's law to bitwise operations
    
    Simplifies expressions using De Morgan's law for bitwise operations:
    - bvnot (bvor (bvnot A) (bvnot B)) -> bvand A B
    """
    
    def __init__(self, enabled: bool = True, max_iterations: int = 10):
        super().__init__("Bitwise De Morgan Simplification", enabled=enabled)
        self.max_iterations = max_iterations
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Apply De Morgan's law to simplify bitwise operations"""
        if not self.enabled:
            return subspec
        
        result = subspec
        changed = True
        iteration = 0
        
        while changed and iteration < self.max_iterations:
            changed = False
            iteration += 1
            original = result
            
            # Find all occurrences of (bvnot (bvor (bvnot ...) (bvnot ...)))
            i = 0
            while i < len(result):
                if result[i] == '(':
                    j = i + 1
                    while j < len(result) and result[j].isspace():
                        j += 1
                    
                    if j + 5 < len(result) and result[j:j+5] == 'bvnot':
                        bvnot_start = i
                        bvnot_end = find_matching_paren(result, bvnot_start)
                        
                        if bvnot_end > 0:
                            inner_start = bvnot_start + 7  # Skip "(bvnot "
                            while inner_start < bvnot_end and result[inner_start].isspace():
                                inner_start += 1
                            
                            if inner_start + 5 <= bvnot_end and result[inner_start] == '(':
                                if inner_start + 1 < len(result) and result[inner_start+1:inner_start+5] == 'bvor':
                                    bvor_start = inner_start
                                    bvor_end = find_matching_paren(result, bvor_start)
                                    
                                    if bvor_end > 0 and bvor_end < bvnot_end:
                                        bvor_content = result[bvor_start+5:bvor_end].strip()
                                        args = self._extract_bvnot_args(bvor_content)
                                        
                                        if len(args) == 2:
                                            replacement = f"(bvand {args[0]} {args[1]})"
                                            result = result[:bvnot_start] + replacement + result[bvnot_end+1:]
                                            changed = True
                                            i = 0
                                            continue
                
                i += 1
            
            if result == original:
                changed = False
        
        if iteration >= self.max_iterations:
            logger.warning(f"    [{self.name}] Reached max iterations ({self.max_iterations})")
        
        if result != subspec:
            logger.info(f"    [{self.name}] Applied De Morgan's law to simplify bitwise operations")
        
        return result
    
    def _extract_bvnot_args(self, content: str) -> List[str]:
        """Extract arguments from bvor content: (bvnot A) (bvnot B)"""
        args = []
        i = 0
        
        while i < len(content):
            while i < len(content) and content[i].isspace():
                i += 1
            
            if i >= len(content):
                break
            
            if content[i] == '(':
                j = i + 1
                while j < len(content) and content[j].isspace():
                    j += 1
                
                if j + 5 < len(content) and content[j:j+5] == 'bvnot':
                    bvnot_start = i
                    bvnot_end = find_matching_paren(content, bvnot_start)
                    
                    if bvnot_end > 0:
                        inner_start = j + 6  # Skip 'bvnot'
                        while inner_start < bvnot_end and content[inner_start].isspace():
                            inner_start += 1
                        inner = content[inner_start:bvnot_end].strip()
                        args.append(inner)
                        i = bvnot_end + 1
                    else:
                        break
                else:
                    i += 1
            else:
                i += 1
        
        return args


class LogicalDeMorganRule(NormalizationRule):
    """Rule 4: Apply De Morgan's law to logical operations
    
    Applies De Morgan's laws to logical expressions:
    - (not (not X)) -> X (double negation elimination)
    - (not (or A B C)) -> (and (not A) (not B) (not C))
    - (or (not A) (not B) ...) -> (not (and A B ...))
    - (or A (not B) (not C) ...) -> (not (and (not A) B C ...))
    """
    
    def __init__(self, enabled: bool = True, max_iterations: int = 10):
        super().__init__("Logical De Morgan Simplification", enabled=enabled)
        self.max_iterations = max_iterations
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Apply De Morgan's law to simplify logical operations"""
        if not self.enabled:
            return subspec
        
        result = subspec
        iteration = 0
        changed = True
        
        while changed and iteration < self.max_iterations:
            iteration += 1
            changed = False
            original = result
            
            # Rule 1: (not (not X)) -> X
            i = 0
            while i < len(result):
                if result[i] == '(' and i + 1 < len(result) and result[i+1:i+5] == 'not ':
                    not_start = i
                    not_end = find_matching_paren(result, not_start)
                    
                    if not_end > 0:
                        inner_start = i + 5  # Skip "(not "
                        while inner_start < not_end and result[inner_start].isspace():
                            inner_start += 1
                        
                        if inner_start < not_end and result[inner_start] == '(':
                            inner_not_start = inner_start
                            j = inner_not_start + 1
                            while j < not_end and result[j].isspace():
                                j += 1
                            
                            if j + 3 < not_end and result[j:j+3] == 'not':
                                inner_not_end = find_matching_paren(result, inner_not_start)
                                if inner_not_end > 0 and inner_not_end < not_end:
                                    x_start = j + 3  # Skip 'not'
                                    while x_start < inner_not_end and result[x_start].isspace():
                                        x_start += 1
                                    x_content = result[x_start:inner_not_end].strip()
                                    
                                    replacement = x_content
                                    result = result[:not_start] + replacement + result[not_end+1:]
                                    changed = True
                                    i = 0
                                    continue
                
                i += 1
            
            # Rule 2: (not (or A B C)) -> (and (not A) (not B) (not C))
            i = 0
            while i < len(result):
                if result[i] == '(' and i + 1 < len(result) and result[i+1:i+5] == 'not ':
                    not_start = i
                    not_end = find_matching_paren(result, not_start)
                    
                    if not_end > 0:
                        inner_start = i + 5  # Skip "(not "
                        while inner_start < not_end and result[inner_start].isspace():
                            inner_start += 1
                        
                        if inner_start < not_end and result[inner_start] == '(':
                            j = inner_start + 1
                            while j < not_end and result[j].isspace():
                                j += 1
                            
                            if j + 2 < not_end and result[j:j+2] == 'or':
                                or_start = inner_start
                                or_end = find_matching_paren(result, or_start)
                                
                                if or_end > 0 and or_end < not_end:
                                    or_content = result[or_start+3:or_end].strip()  # Skip "(or "
                                    args = self._extract_or_args(or_content)
                                    
                                    if len(args) >= 2:
                                        not_args = [f"(not {arg})" for arg in args]
                                        replacement = f"(and {' '.join(not_args)})"
                                        result = result[:not_start] + replacement + result[not_end+1:]
                                        changed = True
                                        i = 0
                                        continue
                
                i += 1
            
            # Rule 3: Universal OR-to-NOT-AND conversion
            # Convert (or ...) to (not (and ...)) for better readability
            # General rule: For each argument in (or ...):
            #   - If it's (not X), add X to (and ...)
            #   - If it's not (not ...), add (not X) to (and ...)
            # Exception: If ALL arguments are NOT (not ...), keep (or ...) unchanged
            # This handles all cases:
            #   - (or (not A) (not B)) -> (not (and A B))
            #   - (or A (not B)) -> (not (and (not A) B))
            #   - (or (not A) B) -> (not (and A (not B)))
            #   - (or (not A) (not B) C) -> (not (and A B (not C)))
            #   - (or A B) -> (or A B) (unchanged, no (not ...) args)
            i = 0
            while i < len(result):
                if result[i] == '(' and i + 2 < len(result) and result[i+1:i+3] == 'or':
                    or_start = i
                    or_end = find_matching_paren(result, or_start)
                    
                    if or_end > 0:
                        or_content = result[or_start+3:or_end].strip()  # Skip "(or "
                        args = self._extract_or_args(or_content)
                        
                        if len(args) >= 2:
                            # Check if at least one argument is (not ...)
                            has_not_arg = any(self._is_not_expr(arg) for arg in args)
                            
                            # Only convert if at least one argument is (not ...)
                            if has_not_arg:
                                # Convert each argument:
                                # - (not X) -> X
                                # - X -> (not X)
                                and_args = []
                                for arg in args:
                                    if self._is_not_expr(arg):
                                        # Extract inner expression from (not X)
                                        inner = self._extract_not_arg(arg)
                                        and_args.append(inner)
                                    else:
                                        # Wrap non-not argument with (not ...)
                                        and_args.append(f"(not {arg})")
                                
                                # Build replacement: (not (and ...))
                                replacement = f"(not (and {' '.join(and_args)}))"
                                result = result[:or_start] + replacement + result[or_end+1:]
                                changed = True
                                i = 0
                                continue
                
                i += 1
            
            if result == original:
                changed = False
        
        if iteration >= self.max_iterations:
            logger.warning(f"    [{self.name}] Reached max iterations ({self.max_iterations})")
        
        if result != subspec:
            logger.info(f"    [{self.name}] Applied De Morgan's law to simplify logical operations")
        
        return result
    
    def _is_not_expr(self, expr: str) -> bool:
        """Check if an expression is a (not ...) form"""
        expr = expr.strip()
        if not expr.startswith('('):
            return False
        
        i = 1
        while i < len(expr) and expr[i].isspace():
            i += 1
        
        return i + 3 <= len(expr) and expr[i:i+3] == 'not'
    
    def _extract_not_arg(self, not_expr: str) -> str:
        """Extract the inner expression from (not X) -> X"""
        not_expr = not_expr.strip()
        if not not_expr.startswith('(not '):
            return not_expr
        
        start = 5  # Skip "(not "
        while start < len(not_expr) and not_expr[start].isspace():
            start += 1
        
        not_end = find_matching_paren(not_expr, 0)
        if not_end > 0:
            inner = not_expr[start:not_end].strip()
            return inner
        
        return not_expr[5:-1].strip()
    
    def _extract_or_args(self, content: str) -> List[str]:
        """Extract arguments from an (or ...) expression"""
        args = []
        i = 0
        
        while i < len(content):
            while i < len(content) and content[i].isspace():
                i += 1
            
            if i >= len(content):
                break
            
            if content[i] == '(':
                start = i
                end = find_matching_paren(content, start)
                
                if end > 0:
                    args.append(content[start:end+1].strip())
                    i = end + 1
                else:
                    break
            else:
                start = i
                while i < len(content) and not content[i].isspace() and content[i] != '(':
                    i += 1
                if i > start:
                    args.append(content[start:i].strip())
        
        return args


class ComparisonConstraintReorderingRule(NormalizationRule):
    """Rule 0: Reorder comparison constraints for better readability
    
    Reorders comparison constraints to a standard order:
    - For the same variable: >= / > constraints first (lower bounds), then <= / < constraints (upper bounds)
    - Then other constraints
    
    Example:
    - (<= Config_XXX 32) AND (>= Config_XXX 24) -> (>= Config_XXX 24) AND (<= Config_XXX 32)
    """
    
    def __init__(self, enabled: bool = True):
        super().__init__("Comparison Constraint Reordering", enabled=enabled)
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Reorder comparison constraints"""
        if not self.enabled:
            return subspec
        
        if " AND " not in subspec:
            return subspec
        
        # Split by " AND "
        parts = [part.strip() for part in subspec.split(" AND ") if part.strip()]
        if len(parts) < 2:
            return subspec
        
        # Pattern to match comparison constraints
        pattern = re.compile(r'\((>=|<=|>|<)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\s+(-?\d+)\)')
        
        comparison_parts = []
        other_parts = []
        
        for part in parts:
            match = pattern.match(part)
            if match:
                op = match.group(1)
                var = match.group(2)
                value = int(match.group(3))
                comparison_parts.append((op, var, value, part))
            else:
                other_parts.append(part)
        
        if not comparison_parts:
            return subspec
        
        # Sort comparison constraints:
        # 1. First by variable name
        # 2. Then by operator priority: >=, >, <=, < (for same variable: >=/> first, then <=/<)
        # 3. Then by value
        def sort_key(item):
            op, var, value, _ = item
            # Operator priority: >= (0), > (1), <= (2), < (3)
            # This ensures for the same variable: >=/> constraints come before <=/< constraints
            op_priority = {'>=': 0, '>': 1, '<=': 2, '<': 3}.get(op, 4)
            return (var, op_priority, value)
        
        comparison_parts.sort(key=sort_key)
        
        # Reconstruct: comparison constraints first, then other parts
        result_parts = [item[3] for item in comparison_parts] + other_parts
        
        result = " AND ".join(result_parts)
        
        if result != subspec:
            logger.debug(f"    [{self.name}] Reordered comparison constraints")
        
        return result


class RedundantComparisonEliminationRule(NormalizationRule):
    """Rule 1: Eliminate redundant comparison constraints
    
    Removes redundant comparison constraints when multiple constraints on the same variable exist:
    - (>= Config_XXX 0) AND (>= Config_XXX 24) -> (>= Config_XXX 24)  (keep larger value)
    - (<= Config_XXX 32) AND (<= Config_XXX 24) -> (<= Config_XXX 24)  (keep smaller value)
    - (> Config_XXX 0) AND (> Config_XXX 24) -> (> Config_XXX 24)    (keep larger value)
    - (< Config_XXX 32) AND (< Config_XXX 24) -> (< Config_XXX 24)    (keep smaller value)
    
    Handles all comparison operators: >=, <=, >, <
    """
    
    def __init__(self, enabled: bool = True):
        super().__init__("Redundant Comparison Elimination", enabled=enabled)
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Eliminate redundant comparison constraints"""
        if not self.enabled:
            return subspec
        
        if " AND " not in subspec:
            return subspec
        
        # Split by " AND "
        parts = [part.strip() for part in subspec.split(" AND ") if part.strip()]
        if len(parts) < 2:
            return subspec
        
        # Group constraints by variable and operator
        # Structure: {variable: {operator: [values]}}
        constraints_by_var = {}
        
        # Pattern to match comparison constraints: (>= var value), (<= var value), (> var value), (< var value)
        pattern = re.compile(r'\((>=|<=|>|<)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\s+(-?\d+)\)')
        
        remaining_parts = []
        for part in parts:
            match = pattern.match(part)
            if match:
                op = match.group(1)
                var = match.group(2)
                value = int(match.group(3))
                
                if var not in constraints_by_var:
                    constraints_by_var[var] = {}
                if op not in constraints_by_var[var]:
                    constraints_by_var[var][op] = []
                constraints_by_var[var][op].append((value, part))
            else:
                # Not a comparison constraint, keep it
                remaining_parts.append(part)
        
        # Process each variable's constraints
        for var, ops_dict in constraints_by_var.items():
            for op, value_list in ops_dict.items():
                if len(value_list) > 1:
                    # Multiple constraints with same operator on same variable
                    if op in ['>=', '>']:
                        # For >= and >, keep the largest value (strongest constraint)
                        value_list.sort(key=lambda x: x[0], reverse=True)
                        # Keep only the first (largest) one
                        remaining_parts.append(value_list[0][1])
                        logger.debug(f"    [{self.name}] Removed redundant {op} constraints for {var}, kept {value_list[0][0]}")
                    elif op in ['<=', '<']:
                        # For <= and <, keep the smallest value (strongest constraint)
                        value_list.sort(key=lambda x: x[0])
                        # Keep only the first (smallest) one
                        remaining_parts.append(value_list[0][1])
                        logger.debug(f"    [{self.name}] Removed redundant {op} constraints for {var}, kept {value_list[0][0]}")
                else:
                    # Only one constraint, keep it
                    remaining_parts.append(value_list[0][1])
        
        if len(remaining_parts) == len(parts):
            # No changes
            return subspec
        
        # Reconstruct the subspec
        result = " AND ".join(remaining_parts)
        
        if result != subspec:
            logger.debug(f"    [{self.name}] Eliminated redundant comparison constraints")
        
        return result


class ComparisonOperatorNormalizationRule(NormalizationRule):
    """Rule 5: Normalize comparison operators to standard form
    
    Converts:
    - (>= constant variable) -> (<= variable constant)
    - (<= constant variable) -> (>= variable constant)
    - (> constant variable) -> (< variable constant)
    - (< constant variable) -> (> variable constant)
    """
    
    def __init__(self, enabled: bool = True):
        super().__init__("Comparison Operator Normalization", enabled=enabled)
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Normalize comparison operators"""
        if not self.enabled:
            return subspec
        
        result = subspec
        
        pattern_ge = re.compile(r'\(>=\s+(\d+)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\)')
        def replace_ge(match):
            return f"(<= {match.group(2)} {match.group(1)})"
        result = pattern_ge.sub(replace_ge, result)
        
        pattern_le = re.compile(r'\(<=\s+(\d+)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\)')
        def replace_le(match):
            return f"(>= {match.group(2)} {match.group(1)})"
        result = pattern_le.sub(replace_le, result)
        
        pattern_gt = re.compile(r'\(>\s+(\d+)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\)')
        def replace_gt(match):
            return f"(< {match.group(2)} {match.group(1)})"
        result = pattern_gt.sub(replace_gt, result)
        
        pattern_lt = re.compile(r'\(<\s+(\d+)\s+((?:Config_[a-zA-Z0-9_-]+|\|[^|]+\|))\)')
        def replace_lt(match):
            return f"(> {match.group(2)} {match.group(1)})"
        result = pattern_lt.sub(replace_lt, result)
        
        if result != subspec:
            logger.debug(f"    [{self.name}] Normalized comparison operators")
        
        return result


def _extract_next_smt_arg(text: str, start: int) -> Tuple[Optional[str], int]:
    """Extract the next SMT argument starting at start; return (arg, next_index)."""
    i = start
    while i < len(text) and text[i].isspace():
        i += 1
    if i >= len(text):
        return None, i
    if text[i] == '(':
        end = find_matching_paren(text, i)
        if end < 0:
            return None, i
        return text[i:end + 1], end + 1
    j = i
    while j < len(text) and not text[j].isspace():
        j += 1
    return text[i:j], j


class IteEqualitySimplificationRule(NormalizationRule):
    """Simplify equalities involving ite when the result matches a branch.

    When A != B:
    - (= (ite C A B) A) -> C
    - (= (ite C A B) B) -> (not C)

    Also handles reversed operand order: (= A (ite C A B)), (= B (ite C A B)).
    """

    def __init__(self, enabled: bool = True, max_iterations: int = 10):
        super().__init__("Ite Equality Simplification", enabled=enabled)
        self.max_iterations = max_iterations

    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        if not self.enabled:
            return subspec

        if " AND " in subspec:
            parts = [part.strip() for part in subspec.split(" AND ") if part.strip()]
            if not parts:
                return subspec
            simplified_parts = [self._simplify_part(part) for part in parts]
            result = " AND ".join(simplified_parts)
        else:
            result = self._simplify_part(subspec)

        if result != subspec:
            logger.info(f"    [{self.name}] Simplified ite equality constraint(s)")
        return result

    def _simplify_part(self, expr: str) -> str:
        result = expr
        changed = True
        iteration = 0

        while changed and iteration < self.max_iterations:
            iteration += 1
            changed = False
            i = 0
            while i < len(result):
                if result[i] == '(':
                    j = i + 1
                    while j < len(result) and result[j].isspace():
                        j += 1
                    if j < len(result) and result[j] == '=':
                        eq_start = i
                        eq_end = find_matching_paren(result, eq_start)
                        if eq_end > 0:
                            eq_expr = result[eq_start:eq_end + 1]
                            simplified = self._try_simplify_ite_equality(eq_expr)
                            if simplified is not None and simplified != eq_expr:
                                result = result[:eq_start] + simplified + result[eq_end + 1:]
                                changed = True
                                i = 0
                                continue
                i += 1

        if iteration >= self.max_iterations:
            logger.warning(f"    [{self.name}] Reached max iterations ({self.max_iterations})")
        return result

    def _try_simplify_ite_equality(self, eq_expr: str) -> Optional[str]:
        lhs, rhs = self._parse_equality(eq_expr)
        if lhs is None or rhs is None:
            return None

        ite_side, other = None, None
        if self._parse_ite(lhs) is not None:
            ite_side, other = lhs, rhs
        elif self._parse_ite(rhs) is not None:
            ite_side, other = rhs, lhs
        else:
            return None

        parsed = self._parse_ite(ite_side)
        if parsed is None:
            return None
        c, a, b = parsed
        if self._expr_equal(a, b):
            return None

        if self._expr_equal(other, a):
            return c
        if self._expr_equal(other, b):
            return self._wrap_not(c)
        return None

    def _parse_equality(self, expr: str) -> Tuple[Optional[str], Optional[str]]:
        expr = expr.strip()
        if not expr.startswith('('):
            return None, None
        end = find_matching_paren(expr, 0)
        if end < 0 or end != len(expr) - 1:
            return None, None

        inner = expr[1:end]
        i = 0
        while i < len(inner) and inner[i].isspace():
            i += 1
        if i >= len(inner) or inner[i] != '=':
            return None, None
        i += 1

        lhs, i = _extract_next_smt_arg(inner, i)
        rhs, _ = _extract_next_smt_arg(inner, i)
        if lhs is None or rhs is None:
            return None, None
        return lhs, rhs

    def _parse_ite(self, expr: str) -> Optional[Tuple[str, str, str]]:
        expr = expr.strip()
        if not expr.startswith('('):
            return None
        end = find_matching_paren(expr, 0)
        if end < 0 or end != len(expr) - 1:
            return None

        inner = expr[1:end]
        i = 0
        while i < len(inner) and inner[i].isspace():
            i += 1
        if i + 3 > len(inner) or inner[i:i + 3] != 'ite':
            return None
        i += 3

        c, i = _extract_next_smt_arg(inner, i)
        a, i = _extract_next_smt_arg(inner, i)
        b, _ = _extract_next_smt_arg(inner, i)
        if c is None or a is None or b is None:
            return None
        return c, a, b

    def _expr_equal(self, a: str, b: str) -> bool:
        return a.strip() == b.strip()

    def _wrap_not(self, expr: str) -> str:
        return f"(not {expr.strip()})"


class ConstraintRedundancyEliminationRule(NormalizationRule):
    """Rule 3: Eliminate redundant extract constraints using target dst-ip constraint
    
    Strategy:
    1. Use provided target_dst_ip to construct target dst-ip constraint
    2. Use target constraint to simplify all other dst-ip extract constraints:
       - Case1: Compatible (other prefix shorter) → simplify to true
       - Case2, 3, 5: Contradictory → simplify to false
       - Case4, 6: Keep unchanged (exact match or cannot determine)
    
    Example:
    - Input: (let ((a!1 (not (or (= ((_ extract 31 12) |0_dst-ip|) #xc0006) 
                                  (= ((_ extract 31 12) |0_dst-ip|) #xc6336))))) ...)
    - target_dst_ip: "198.51.100.0/24"
    - Target constraint: (= ((_ extract 31 8) |0_dst-ip|) #xc63364)
    - Output: Simplified expression with extract 31 12 constraints evaluated
    """
    
    def __init__(self, enabled: bool = True, target_dst_ip: Optional[str] = None):
        """Initialize the rule
        
        Args:
            enabled: Whether the rule is enabled
            target_dst_ip: Optional IP/mask string (e.g., "192.0.2.0/24" or "192.0.2.0/25")
                          Used to construct target dst-ip constraint
        """
        super().__init__("Constraint Redundancy Elimination", enabled=enabled)
        self.target_dst_ip = target_dst_ip
        self.target_dst_ip_constraint = None
        self.target_dst_ip_network = None
        if target_dst_ip:
            self.target_dst_ip_constraint = self._construct_target_dst_ip_constraint(target_dst_ip)
            # Also store the network object for prefix comparison
            try:
                import ipaddress
                self.target_dst_ip_network = ipaddress.ip_network(target_dst_ip, strict=False)
            except (ValueError, ImportError):
                pass
    
    def _construct_target_dst_ip_constraint(self, ip_mask: str) -> Optional[Tuple[int, int, str, str]]:
        """Construct target dst-ip constraint from IP/mask string
        
        Args:
            ip_mask: IP/mask string (e.g., "192.0.2.0/24" or "192.0.2.0/25")
            
        Returns:
            (high_bit, low_bit, variable, value) tuple or None if parsing fails
        """
        from utils.util_smt import prefix_string_to_constraint_tuple
        
        # Use the utility function to get the constraint tuple
        result = prefix_string_to_constraint_tuple(ip_mask)
        if not result:
            logger.warning(f"    [{self.name}] Failed to parse target_dst_ip '{ip_mask}'")
            return None
        
        return result
    
    def _parse_hex_value(self, val_str: str) -> Optional[int]:
        """Parse hexadecimal value string
        
        Args:
            val_str: Value string (e.g., "#xc63364", "0xc63364")
            
        Returns:
            Integer value or None if parsing fails
        """
        try:
            if val_str.startswith('#x'):
                return int(val_str[2:], 16)
            elif val_str.startswith('0x'):
                return int(val_str[2:], 16)
            elif val_str.startswith('#b'):
                return int(val_str[2:], 2)
            else:
                return None
        except (ValueError, AttributeError):
            return None
    
    def _extract_constraint_to_prefix(self, constraint: Tuple[int, int, str, str]) -> Optional[Tuple[int, int]]:
        """Extract prefix information from an extract constraint
        
        Args:
            constraint: (high_bit, low_bit, variable, value) constraint
            
        Returns:
            (prefix_value, prefix_length) tuple or None if parsing fails
            prefix_value: The value of the prefix bits (as integer)
            prefix_length: The length of the prefix (number of bits)
        """
        high, low, var, val = constraint
        
        # Calculate prefix length: extract [31, low] means prefix_length = 32 - low
        prefix_length = 32 - low
        
        # Parse the value
        val_int = self._parse_hex_value(val)
        if val_int is None:
            return None
        
        # The value represents the prefix bits
        prefix_value = val_int
        
        return (prefix_value, prefix_length)
    
    def _evaluate_constraint(self, constraint: Tuple[int, int, str, str], 
                            key_target: Tuple[int, int, str, str]) -> Optional[bool]:
        """Evaluate a constraint against key target using prefix comparison logic
        
        Logic:
        - Case 1/2: other prefix_length < target prefix_length
          - Compare first other_prefix_length bits (use other prefix length)
          - If same -> True (case1)
          - If different -> False (case2)
        - Case 3/4: other prefix_length = target prefix_length
          - Compare directly (same length)
          - If same -> None (keep unchanged, case4)
          - If different -> False (case3)
        - Case 5/6: other prefix_length > target prefix_length
          - Compare first target_prefix_length bits (use target prefix length)
          - If same -> None (cannot determine, case6)
          - If different -> False (case5)
        
        Args:
            constraint: (high_bit, low_bit, variable, value) to evaluate
            key_target: (high_bit, low_bit, variable, value) key target constraint
            
        Returns:
            True if constraint is compatible with key target
            False if constraint contradicts key target
            None if cannot determine or should keep unchanged
        """
        high1, low1, var1, val1 = constraint
        high2, low2, var2, val2 = key_target
        
        # Must be same variable
        if var1 != var2:
            return None
        
        # Both must start at the same high bit (31 for IPv4)
        if high1 != high2 or high1 != 31:
            return None
        
        # Calculate prefix lengths
        other_prefix_length = 32 - low1
        target_prefix_length = 32 - low2
        
        # Parse values
        val1_int = self._parse_hex_value(val1)
        val2_int = self._parse_hex_value(val2)
        
        if val1_int is None or val2_int is None:
            return None
        
        # Case 3/4: other prefix_length = target prefix_length
        if other_prefix_length == target_prefix_length:
            if val1_int == val2_int:
                # Case 4: Exactly same -> keep unchanged
                return None
            else:
                # Case 3: Same length but different values -> contradiction
                return False
        
        # Case 1/2: other prefix_length < target prefix_length
        # Compare using other_prefix_length bits
        elif other_prefix_length < target_prefix_length:
            # Extract other_prefix_length bits from target constraint
            # target constraint has target_prefix_length bits, we need the high other_prefix_length bits
            shift_amount = target_prefix_length - other_prefix_length
            target_prefix_bits = (val2_int >> shift_amount) & ((1 << other_prefix_length) - 1)
            other_prefix_bits = val1_int & ((1 << other_prefix_length) - 1)
            
            if other_prefix_bits == target_prefix_bits:
                # Case 1: Compatible -> True
                return True
            else:
                # Case 2: Contradictory -> False
                return False
        
        # Case 5/6: other prefix_length > target prefix_length
        # Compare using target_prefix_length bits
        else:  # other_prefix_length > target_prefix_length
            # Extract target_prefix_length bits from other constraint
            # other constraint has other_prefix_length bits, we need the high target_prefix_length bits
            shift_amount = other_prefix_length - target_prefix_length
            other_prefix_bits = (val1_int >> shift_amount) & ((1 << target_prefix_length) - 1)
            target_prefix_bits = val2_int & ((1 << target_prefix_length) - 1)
            
            if other_prefix_bits == target_prefix_bits:
                # Case 6: Cannot determine (more specific than target) -> keep unchanged
                return None
            else:
                # Case 5: Contradictory -> False
                return False
    
    def _find_all_extract_constraints(self, expr: str) -> List[Tuple[int, str, Tuple[int, int, str, str]]]:
        """Find all extract constraints in expression with their positions
        
        Args:
            expr: SMT expression
            
        Returns:
            List of (start_pos, constraint_str, (high_bit, low_bit, variable, value)) tuples
        """
        constraints = []
        # Pattern: (= ((_ extract HIGH LOW) VAR) VALUE)
        pattern = re.compile(r'\(=\s+\(\(_\s+extract\s+(\d+)\s+(\d+)\)\s+([^)]+)\)\s+([^)]+)\)')
        
        for match in pattern.finditer(expr):
            start_pos = match.start()
            constraint_str = match.group(0)
            high_bit = int(match.group(1))
            low_bit = int(match.group(2))
            variable = match.group(3).strip()
            value = match.group(4).strip()
            constraints.append((start_pos, constraint_str, (high_bit, low_bit, variable, value)))
        
        return constraints
    
    def _replace_constraint_smart(self, expr: str, constraint_str: str, start_pos: int, 
                                   replacement: str) -> str:
        """Replace constraint with replacement, handling surrounding context
        
        Args:
            expr: Full expression
            constraint_str: The constraint string to replace
            start_pos: Start position of constraint
            replacement: Replacement value ("true" or "false")
            
        Returns:
            Modified expression
        """
        # Check if constraint is negated: (not constraint_str)
        if start_pos >= 3 and expr[start_pos-4:start_pos] == "(not":
            # Find the matching closing paren for (not ...)
            not_start = start_pos - 4
            not_end = find_matching_paren(expr, not_start)
            if not_end > 0:
                # Replace (not constraint) with opposite
                opposite = "false" if replacement == "true" else "true"
                return expr[:not_start] + opposite + expr[not_end+1:]
        
        # Direct replacement
        return expr[:start_pos] + replacement + expr[start_pos + len(constraint_str):]
    
    def apply(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Eliminate redundant extract constraints using target dst-ip constraint"""
        if not self.enabled:
            return subspec
        
        # Only use target_dst_ip_constraint if provided
        if not self.target_dst_ip_constraint:
            return subspec
        
        high, low, var, val = self.target_dst_ip_constraint
        logger.debug(f"    [{self.name}] Using target_dst_ip constraint: extract {high} {low} = {val}")
        
        key_target = self.target_dst_ip_constraint
        
        # Find all extract constraints in the expression
        all_constraints = self._find_all_extract_constraints(subspec)
        
        if not all_constraints:
            return subspec
        
        # Process constraints from end to start to avoid position shifts
        result = subspec
        changes_made = False
        
        for start_pos, constraint_str, constraint in reversed(all_constraints):
            high, low, var, val = constraint
            
            # Only process constraints for the same variable as target
            key_high, key_low, key_var, key_val = key_target
            if var != key_var:
                continue
            
            # Skip if this is the target constraint itself (exact match)
            if high == key_high and low == key_low and val == key_val:
                continue  # This is the target constraint itself, keep unchanged
            
            # Evaluate constraint against target
            evaluation = self._evaluate_constraint(constraint, key_target)
            
            if evaluation is True:
                # Case1: Constraint is compatible with target (other prefix shorter and compatible)
                # Simplify to true
                result = self._replace_constraint_smart(result, constraint_str, start_pos, "true")
                changes_made = True
                logger.debug(f"    [{self.name}] Simplified compatible constraint to true: {constraint_str}")
            elif evaluation is False:
                # Case2, 3, 5: Constraint contradicts target → simplify to false
                result = self._replace_constraint_smart(result, constraint_str, start_pos, "false")
                changes_made = True
                logger.debug(f"    [{self.name}] Simplified contradicting constraint to false: {constraint_str}")
            # If evaluation is None (Case4, Case6), keep unchanged
        
        if changes_made:
            logger.info(f"    [{self.name}] Applied constraint redundancy elimination using key targets")
        
        return result


class NormalizationRuleManager:
    """Manager for normalization rules
    
    This class manages a collection of normalization rules and applies them
    in the order they were added. Rules can be enabled/disabled and new rules can be
    easily added.
    """
    
    def __init__(self, rules: Optional[List[NormalizationRule]] = None):
        """Initialize the rule manager
        
        Args:
            rules: Optional list of rules. If None, creates empty rule list.
        """
        if rules is None:
            self.rules = []
        else:
            self.rules = rules
    
    def add_rule(self, rule: NormalizationRule):
        """Add a new rule to the manager (appended to the end)"""
        self.rules.append(rule)
        logger.info(f"Added normalization rule: {rule}")
    
    def remove_rule(self, rule_name: str):
        """Remove a rule by name"""
        self.rules = [r for r in self.rules if r.name != rule_name]
        logger.info(f"Removed normalization rule: {rule_name}")
    
    def enable_rule(self, rule_name: str):
        """Enable a rule by name"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"Enabled rule: {rule_name}")
                return
        logger.warning(f"Rule not found: {rule_name}")
    
    def disable_rule(self, rule_name: str):
        """Disable a rule by name"""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"Disabled rule: {rule_name}")
                return
        logger.warning(f"Rule not found: {rule_name}")
    
    def apply_all(self, subspec: str, context: Optional[Dict] = None) -> str:
        """Apply all enabled rules to a subspec in order
        
        Args:
            subspec: The subspec string to normalize
            context: Optional context dictionary (e.g., containing helper methods)
            
        Returns:
            Normalized subspec string after applying all rules
        """
        result = subspec
        
        for rule in self.rules:
            if rule.enabled:
                try:
                    result = rule.apply(result, context)
                except Exception as e:
                    logger.error(f"Error applying rule {rule.name}: {e}")
                    # Continue with other rules even if one fails
        
        return result
    
    def get_rules_info(self) -> List[Dict]:
        """Get information about all registered rules"""
        return [
            {
                'name': rule.name,
                'class': rule.__class__.__name__,
                'enabled': rule.enabled
            }
            for rule in self.rules
        ]


def normalizer1(subspec: str, target_dst_ip: Optional[str] = None) -> str:
    """Normalizer 1: Apply rules in order (no let expansion here; let expand is done at the end of normalize_subspec).
    1. ComparisonOperatorNormalizationRule - Normalize comparison operators
    2. IteEqualitySimplificationRule - Simplify (= (ite C A B) T) when T is A or B
    3. ConstraintRedundancyEliminationRule - Eliminate redundant constraints
    
    Args:
        subspec: The subspec string to normalize
        target_dst_ip: Optional IP/mask string (e.g., "192.0.2.0/24" or "192.0.2.0/25")
                       Used to construct target dst-ip constraint for simplification
        
    Returns:
        Normalized subspec string
    """
    rules = [
        ComparisonOperatorNormalizationRule(),
        IteEqualitySimplificationRule(),
        ConstraintRedundancyEliminationRule(target_dst_ip=target_dst_ip),
    ]
    
    result = subspec
    for rule in rules:
        if rule.enabled:
            try:
                result = rule.apply(result)
            except Exception as e:
                logger.error(f"Error applying rule {rule.name}: {e}")
                # Continue with other rules even if one fails
    
    return result


def normalizer2(subspec: str) -> str:
    """Normalizer 2: Run after iteration is done (no more iterations). Apply rules in order:
    0. LetExpressionExpansionRule - Expand let expressions (once, at start of final pass)
    1. ComparisonConstraintReorderingRule - Reorder comparison constraints
    2. RedundantComparisonEliminationRule - Eliminate redundant comparison constraints
    3. BitwiseDeMorganRule - Apply De Morgan's law to bitwise operations
    4. LogicalDeMorganRule - Apply De Morgan's law to logical operations
    
    Args:
        subspec: The subspec string to normalize
        
    Returns:
        Normalized subspec string
    """
    rules = [
        LetExpressionExpansionRule(),
        ComparisonConstraintReorderingRule(),
        RedundantComparisonEliminationRule(),
        BitwiseDeMorganRule(),
        LogicalDeMorganRule(),
    ]
    
    result = subspec
    for rule in rules:
        if rule.enabled:
            try:
                result = rule.apply(result)
            except Exception as e:
                logger.error(f"Error applying rule {rule.name}: {e}")
                # Continue with other rules even if one fails
    
    return result


# ---------------------------------------------------------------------------
# Normalizer core: normalize_subspec, _load_metadata_file (for inline use)
# ---------------------------------------------------------------------------


def normalize_subspec(
    subspec: str,
    metadata_file: Path,
    config_name: str,
    is_field_level: bool = True,
    is_pair: bool = False,
    target_dst_ip: Optional[str] = None,
    max_iterations: int = 3,
    verbose: bool = False,
    temp_dir: Optional[Path] = None
) -> str:
    """Normalize a single subspec using iterative normalization with Z3 simplification."""
    if subspec == "empty" or not subspec.strip():
        return subspec

    declares, commented_equalities, device = _load_metadata_file(metadata_file)
    if not declares:
        logger.warning(f"No declares found in metadata file {metadata_file}, returning original subspec")
        return subspec

    if not is_field_level:
        all_config_names = _extract_config_vars_from_commented_equalities(commented_equalities)
        check_all_configs = True
    elif is_pair:
        all_config_names = _get_pair_config_names(config_name)
        check_all_configs = True
    else:
        all_config_names = {config_name}
        check_all_configs = False

    base_subspec, community_suffix = _strip_community_suffix(subspec)
    current_subspec = base_subspec
    previous_z3_result = None

    for iteration in range(max_iterations):
        if verbose:
            logger.info(f"Normalizing {config_name}, iteration {iteration + 1}/{max_iterations}")

        after_normalizer1 = normalizer1(current_subspec, target_dst_ip=target_dst_ip)
        if after_normalizer1 == current_subspec:
            if iteration == 0 and after_normalizer1 == base_subspec:
                previous_z3_result = after_normalizer1
            break

        z3_result = _simplify_with_z3(
            after_normalizer1, config_name, metadata_file, declares, commented_equalities,
            all_config_names, check_all_configs, is_field_level, is_pair,
            iteration + 1, device, temp_dir
        )
        if z3_result is None:
            z3_result = after_normalizer1
        if z3_result == previous_z3_result:
            break
        if z3_result == after_normalizer1:
            break
        previous_z3_result = z3_result
        current_subspec = z3_result

    final_input = previous_z3_result if previous_z3_result else after_normalizer1
    final_after_normalizer1 = normalizer1(final_input, target_dst_ip=target_dst_ip)
    final_result = normalizer2(final_after_normalizer1)
    final_result_with_suffix = _merge_community_suffix(final_result, community_suffix)
    return final_result_with_suffix


def _load_metadata_file(metadata_file: Path) -> Tuple[List[str], List[str], Optional[str]]:
    """Load metadata file and extract declares, commented equality constraints, and device name."""
    declares = []
    commented_equalities = []
    device = None
    if not metadata_file.exists():
        return declares, commented_equalities, device
    try:
        with open(metadata_file, 'r') as f:
            in_declares_section = False
            in_commented_section = False
            for line in f:
                line_stripped = line.strip()
                if line_stripped.startswith("; Device:"):
                    device_match = re.search(r'Device:\s*(\S+)', line_stripped)
                    if device_match:
                        device = device_match.group(1)
                if "All VAR type declarations" in line or "declare-fun" in line_stripped:
                    in_declares_section = True
                    in_commented_section = False
                if "All commented Config variable assignments" in line or "commented Config" in line:
                    in_declares_section = False
                    in_commented_section = True
                if in_declares_section and line_stripped.startswith("(declare-fun"):
                    declares.append(line_stripped)
                if in_commented_section and line_stripped.startswith(";") and "(assert" in line_stripped:
                    uncommented = line_stripped.lstrip(";").strip()
                    if uncommented.startswith("(assert"):
                        commented_equalities.append(uncommented)
    except Exception as e:
        logger.warning(f"Failed to read metadata file {metadata_file}: {e}")
    return declares, commented_equalities, device


def _convert_subspec_to_smt2_asserts(subspec: str) -> List[str]:
    if subspec == "empty" or not subspec.strip():
        return []
    if " AND " in subspec:
        return [p.strip() for p in subspec.split(" AND ") if p.strip()]
    return [subspec.strip()]


def _build_smt2_file_with_metadata(
    subspec: str, config_name: str, metadata_file: Path, declares: List[str],
    iteration: int, device: Optional[str], temp_dir: Optional[Path] = None
) -> Optional[Path]:
    if subspec == "empty" or not subspec.strip():
        return None
    assert_exprs = _convert_subspec_to_smt2_asserts(subspec)
    if not assert_exprs:
        return None
    smt_content = [
        "; Z3 Simplification SMT file", f"; Generated for {config_name}", f"; Iteration: {iteration}", "",
        "; Declarations from metadata file"
    ]
    for declare in sorted(set(declares)):
        smt_content.append(declare)
    smt_content.extend(["", "; Assert statements from subspec"])
    for assert_expr in assert_exprs:
        smt_content.append(f"(assert {assert_expr})")
    smt_content.extend(["", "; Apply simplification", "(apply (then simplify propagate-values elim-and solve-eqs ctx-solver-simplify))"])
    out_dir = temp_dir if temp_dir else metadata_file.parent
    safe_name = config_name.replace('/', '_').replace(':', '_').replace(' ', '_')
    output_file = out_dir / (f"compute_subspec_from_{device}_{safe_name}_norm_iter{iteration}.smt2" if device else f"compute_subspec_from_{safe_name}_norm_iter{iteration}.smt2")
    try:
        with open(output_file, 'w') as f:
            f.write('\n'.join(smt_content))
        return output_file
    except Exception as e:
        logger.error(f"Failed to write SMT2 file {output_file}: {e}")
        return None


def _extract_config_vars_from_commented_equalities(commented_equalities: List[str]) -> Set[str]:
    config_vars = set()
    for eq in commented_equalities:
        match = re.search(r'Config_[a-zA-Z0-9_-]+', eq)
        if match:
            config_vars.add(match.group(0))
    return config_vars


def _get_pair_config_names(config_name: str) -> Set[str]:
    if config_name.endswith('__ip'):
        return {config_name, config_name[:-4] + '__mask'}
    if config_name.endswith('__mask'):
        return {config_name[:-6] + '__ip', config_name}
    return {config_name}


def _extract_variables_from_line(line: str) -> Set[str]:
    variables = set()
    variables.update(re.findall(r'\|[^|]+\|', line))
    variables.update(re.findall(r'Config_[a-zA-Z0-9_-]+', line))
    return variables


def _parse_goals_structure(output: str) -> List[Dict[str, str]]:
    lines = output.split('\n')
    goals_data = []
    current_line = ""
    paren_count = 0
    in_goal = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("(goals") or line.startswith("(goal"):
            in_goal = True
            continue
        if not in_goal:
            continue
        for char in line:
            paren_count += 1 if char == '(' else (-1 if char == ')' else 0)
        current_line += " " + line
        if paren_count == 0 and current_line.strip():
            content = current_line.strip()
            if content and content != ")":
                goals_data.append({'content': content, 'line_number': len(goals_data) + 1})
            current_line = ""
    return goals_data


def _extract_config_constraints_from_z3_output(
    z3_output: str, config_names: Set[str], commented_equalities: List[str], check_all_configs: bool = False
) -> str:
    goals_data = _parse_goals_structure(z3_output)
    if not goals_data:
        if commented_equalities:
            result_parts = []
            for eq in commented_equalities:
                match = re.search(r'Config_[a-zA-Z0-9_-]+', eq)
                if match and match.group(0) in config_names and '(= ' in eq:
                    m = re.match(r'\(assert\s+(.+)\)', eq)
                    result_parts.append(m.group(1) if m else eq.replace("(assert ", "").rstrip(")"))
            if result_parts:
                return " AND ".join(result_parts)
        return ""
    config_lines = []
    for line_data in goals_data:
        content = line_data['content'].strip()
        if content and not content.startswith(':') and content not in ['(goal', ')']:
            for cn in config_names:
                if cn in content:
                    config_lines.append(line_data)
                    break
    all_variables = set()
    for line_data in config_lines:
        all_variables.update(_extract_variables_from_line(line_data['content']))
    related_lines = []
    for line_data in goals_data:
        content = line_data['content'].strip()
        if content and not content.startswith(':') and content not in ['(goal', ')']:
            if _extract_variables_from_line(content).intersection(all_variables):
                related_lines.append(line_data)
    constraint_parts = []
    found_config_vars = set()
    for line_data in related_lines:
        content = line_data['content'].strip()
        if content and not content.startswith(':') and content not in ['(goal', ')']:
            if content.startswith("(goal ") or content.startswith("(goal\n"):
                for assertion in _unwrap_goal_content(content):
                    if assertion and assertion != ")":
                        constraint_parts.append(assertion)
                        for cn in config_names:
                            if cn in assertion or ("|" + cn + "|") in assertion:
                                found_config_vars.add(cn)
            else:
                constraint_parts.append(content)
                for cn in config_names:
                    if cn in content or ("|" + cn + "|") in content:
                        found_config_vars.add(cn)
    if check_all_configs:
        missing_configs = config_names - found_config_vars
        if missing_configs:
            for eq in commented_equalities:
                match = re.search(r'Config_[a-zA-Z0-9_-]+', eq)
                if match and match.group(0) in missing_configs and '(= ' in eq:
                    em = re.match(r'\(assert\s+(.+)\)', eq)
                    constraint_parts.append(em.group(1) if em else eq.replace("(assert ", "").rstrip(")"))
    if constraint_parts:
        return " AND ".join(constraint_parts)
    # Fall back to equality constraints when no goal content mentioned config names.
    # Filter by config_names so: field-level = this field only, pair = ip+mask only, line-level = all for line.
    if commented_equalities:
        result_parts = []
        for eq in commented_equalities:
            match = re.search(r'Config_[a-zA-Z0-9_-]+', eq)
            if match and match.group(0) in config_names and '(= ' in eq:
                m = re.match(r'\(assert\s+(.+)\)', eq)
                result_parts.append(m.group(1) if m else eq.replace("(assert ", "").rstrip(")"))
        if result_parts:
            return " AND ".join(result_parts)
    return ""


def _simplify_with_z3(
    subspec: str, config_name: str, metadata_file: Path, declares: List[str],
    commented_equalities: List[str], all_config_names: Set[str], check_all_configs: bool,
    is_field_level: bool, is_pair: bool, iteration: int, device: Optional[str], temp_dir: Optional[Path] = None
) -> Optional[str]:
    if subspec == "empty" or not subspec.strip():
        return subspec
    smt_file = _build_smt2_file_with_metadata(subspec, config_name, metadata_file, declares, iteration, device, temp_dir)
    if not smt_file:
        return None
    try:
        with open(smt_file, 'r') as f:
            smt_input = f.read()
        result = subprocess.run(['z3', '-smt2', '-in'], input=smt_input, capture_output=True, text=True)
        if result.returncode != 0 or "(error" in result.stdout:
            return None
        simplified = _extract_config_constraints_from_z3_output(
            result.stdout, all_config_names, commented_equalities, check_all_configs=check_all_configs)
        return simplified if simplified else subspec
    except Exception:
        return None


def _strip_community_suffix(subspec: str) -> Tuple[str, Optional[str]]:
    match = re.search(r'\s+AND\s+configurable', subspec, re.IGNORECASE)
    if match:
        base_subspec = re.sub(r'\s+AND\s*$', '', subspec[:match.start()].strip())
        return base_subspec, subspec[match.start():].strip()
    match = re.search(r'\s+AND\s+nonconfigurable', subspec, re.IGNORECASE)
    if match:
        base_subspec = re.sub(r'\s+AND\s*$', '', subspec[:match.start()].strip())
        return base_subspec, subspec[match.start():].strip()
    return subspec, None


def _merge_community_suffix(base_subspec: str, community_suffix: Optional[str]) -> str:
    return f"{base_subspec} {community_suffix}" if community_suffix else base_subspec
