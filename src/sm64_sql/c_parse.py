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

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Set

import tree_sitter_c
from tree_sitter import Language, Parser


@dataclass
class Call:
    callee: str
    args: List[str]
    line: int


@dataclass
class Func:
    name: str
    file: str  # repo-relative
    calls: List[Call] = field(default_factory=list)
    params: List[Optional[str]] = field(default_factory=list)


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
                calls.append(Call(fn.text.decode(), args, node.start_point[0] + 1))
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
                    Func(name, rel, collect_calls(body), function_params(node))
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


def parse_c_functions(path: Path, rel: str) -> List[Func]:
    """Parse one C file into its function definitions and their call sites."""
    return functions_from_tree(get_parser().parse(path.read_bytes()), rel)


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
