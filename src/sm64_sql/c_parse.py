"""Shared tree-sitter primitives for reading the decomp's C source.

The build parses C *function bodies* with tree-sitter (a concrete syntax tree),
not regex, so that completeness is a *structural* property: every
``function_definition`` and every ``call_expression`` is enumerated by the
grammar, with no line-matching to silently miss a multi-line call or a K&R
signature. Two corpora are mined this way -- the relations in each behavior's
native code (``behavior_call``) and Mario's action state machine
(``mario_action``) -- so the parser, the function/call model, and the
reachability walk live here, shared by both.

tree-sitter is a build-time dependency (it produces the database); it never
ships to the web client. It is pinned to 0.21.x in pyproject (its
``Language()`` / ``Parser()`` API differs from 0.22+).
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

import tree_sitter_c
from tree_sitter import Language, Parser

# Preprocessor conditional directives. tree-sitter parses C, not the preprocessor,
# so a directive that splits a brace pair -- e.g. an "#if ENABLE_RUMBLE { #endif
# ... #if ENABLE_RUMBLE } #endif" wrapping an if-block -- leaves the braces
# unbalanced in the token stream and the enclosing function fails to parse,
# silently dropping it (and the calls inside it). Blanking these directive lines
# (keeping their newline, so line numbers are preserved for provenance) restores
# a balanced, parseable body. The guarded code itself is kept -- we want the
# calls it contains -- so this is safe for the no-#else case that dominates the
# decomp; an #if/#else with cross-arm braces would still drop, no worse than now.
_PREPROC_COND = re.compile(
    rb"^[ \t]*#[ \t]*(?:if|ifdef|ifndef|elif|else|endif)\b.*$", re.MULTILINE
)


@dataclass
class Call:
    callee: str
    args: List[str]
    line: int
    condition: Optional[str] = None  # nearest enclosing if-guard (None if none)


@dataclass
class Func:
    name: str
    file: str  # repo-relative
    calls: List[Call] = field(default_factory=list)
    params: List[Optional[str]] = field(default_factory=list)
    line: int = 0  # 1-based line of the definition (provenance)


_parser: Optional[Parser] = None


def get_parser() -> Parser:
    global _parser
    if _parser is None:
        language = Language(tree_sitter_c.language(), "c")
        parser = Parser()
        parser.set_language(language)
        _parser = parser
    return _parser


def function_name(node) -> Optional[str]:
    """Return the identifier of a ``function_definition`` node.

    The name is nested under the ``declarator`` field, possibly wrapped in a
    ``pointer_declarator`` (pointer return type) or ``parenthesized_declarator``;
    descend until the ``identifier`` is reached.
    """
    declarator = node.child_by_field_name("declarator")
    while declarator is not None and declarator.type != "identifier":
        nxt = declarator.child_by_field_name("declarator")
        if nxt is None:
            nxt = next(
                (
                    child
                    for child in declarator.children
                    if child.type
                    in (
                        "function_declarator",
                        "identifier",
                        "pointer_declarator",
                        "parenthesized_declarator",
                    )
                ),
                None,
            )
        declarator = nxt
    return declarator.text.decode() if declarator is not None else None


def function_params(node) -> List[Optional[str]]:
    """Return a function_definition's parameter names (None for an unnamed one).

    Order is preserved, so an argument written as a parameter can be mapped to
    its index and looked up in the caller's arguments.
    """
    declarator = node.child_by_field_name("declarator")
    fdecl = find_descendant(declarator, "function_declarator") if declarator else None
    plist = fdecl.child_by_field_name("parameters") if fdecl is not None else None
    if plist is None:
        return []
    params: List[Optional[str]] = []
    for child in plist.named_children:
        if child.type != "parameter_declaration":
            continue
        pdecl = child.child_by_field_name("declarator")
        ident = find_descendant(pdecl, "identifier") if pdecl is not None else None
        params.append(ident.text.decode() if ident is not None else None)
    return params


def _guard_condition(call_node) -> Optional[str]:
    """The condition under which ``call_node`` runs: the nearest enclosing ``if``.

    Walks up to the innermost ``if_statement`` the call sits inside (stopping at
    the function boundary). A call in the ``else`` branch is negated. The outer
    parentheses are stripped and whitespace collapsed, so the result reads as a
    label -- e.g. ``m->input & INPUT_B_PRESSED`` or ``!(m->vel[1] > 0.0f)``. A
    call guarded by nothing (or by a switch / early-return idiom) returns None.
    """
    child = call_node
    node = call_node.parent
    while node is not None:
        if node.type == "function_definition":
            return None
        if node.type == "if_statement":
            cond = node.child_by_field_name("condition")
            if cond is not None:
                text = " ".join(cond.text.decode().split())
                if text.startswith("(") and text.endswith(")"):
                    text = text[1:-1].strip()
                # We ascended into this if through `child`; if that is the
                # `else` body, the call runs under the negated condition.
                alt = node.child_by_field_name("alternative")
                in_else = alt is not None and child == alt
                return f"!({text})" if in_else else text
        child = node
        node = node.parent
    return None


def collect_calls(body) -> List[Call]:
    """Every ``call_expression`` in a function body, in source (pre-order)."""
    calls: List[Call] = []

    def visit(node) -> None:
        if node.type == "call_expression":
            fn = node.child_by_field_name("function")
            arg_list = node.child_by_field_name("arguments")
            # Only plain named calls: a function-pointer call or a cast that the
            # grammar shapes like a call (e.g. "(s32)(x)") is not a relation.
            if fn is not None and fn.type == "identifier" and arg_list is not None:
                args = [
                    child.text.decode()
                    for child in arg_list.named_children
                    if child.type != "comment"
                ]
                calls.append(
                    Call(
                        fn.text.decode(),
                        args,
                        node.start_point[0] + 1,
                        _guard_condition(node),
                    )
                )
        for child in node.children:
            visit(child)

    visit(body)
    return calls


def functions_from_tree(tree, rel: str) -> List[Func]:
    funcs: List[Func] = []

    def visit(node) -> None:
        if node.type == "function_definition":
            name = function_name(node)
            body = node.child_by_field_name("body")
            if name is not None and body is not None:
                funcs.append(
                    Func(
                        name,
                        rel,
                        collect_calls(body),
                        function_params(node),
                        node.start_point[0] + 1,
                    )
                )
            return  # C has no nested function definitions
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return funcs


def find_descendant(node, node_type):
    if node.type == node_type:
        return node
    for child in node.children:
        found = find_descendant(child, node_type)
        if found is not None:
            return found
    return None


def parse_tree(path: Path, strip_conditionals: bool = False):
    """Parse a C file to a tree-sitter tree.

    With ``strip_conditionals`` the preprocessor conditional directives are
    blanked first (see ``_PREPROC_COND``) so a function whose braces are split
    across an ``#if``/``#endif`` is still parsed.
    """
    src = path.read_bytes()
    if strip_conditionals:
        src = _PREPROC_COND.sub(b"", src)
    return get_parser().parse(src)


def parse_c_functions(path: Path, rel: str) -> List[Func]:
    """Parse one C file into its function definitions and their call sites."""
    return functions_from_tree(parse_tree(path), rel)


def reachable(
    root: str,
    funcs: Dict[str, Func],
    recursion_set: Set[str],
    action_tables: Optional[Dict[str, List[str]]] = None,
    dispatchers: FrozenSet[str] = frozenset(),
) -> Set[str]:
    """Functions reachable from ``root`` through a chosen ``recursion_set``.

    Recursion descends into a callee in ``recursion_set`` (e.g. object-behavior
    functions, or Mario's action code); everything else is a leaf -- the leaves
    are the relation vocabulary, not edges to recurse into. A call to a
    ``dispatchers`` function ``f(table, ...)`` is followed into every function
    its first argument names in ``action_tables`` -- the only way functions
    invoked through a function-pointer table are reached. ``root`` itself is
    always included, even when it lives outside the recursion set (an external
    entry point).
    """
    action_tables = action_tables or {}
    seen = {root}
    stack = [root]

    def enqueue(name: str) -> None:
        if name in recursion_set and name not in seen:
            seen.add(name)
            stack.append(name)

    while stack:
        fn = funcs.get(stack.pop())
        if fn is None:
            continue
        for call in fn.calls:
            enqueue(call.callee)
            if call.callee in dispatchers and call.args:
                for action_fn in action_tables.get(call.args[0], ()):
                    enqueue(action_fn)
    return seen
