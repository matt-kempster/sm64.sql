"""Extract the relations each behavior expresses in its *native C code*.

A behavior script in ``data/behavior_data.c`` mostly just ``CALL_NATIVE``s into
C functions under ``src/game/behaviors/*.inc.c``. The real logic -- what an
object spawns, the sounds it plays, the dialog it shows, the behavior it morphs
into -- lives in those functions and the helpers they call, and the behavior
script never names any of it. ``behavior_command`` captures the script; this
captures the code beneath it.

The C is parsed with tree-sitter (a concrete syntax tree), not regex, so that
completeness is a *structural* property: every ``function_definition`` and every
``call_expression`` is enumerated by the grammar, with no line-matching to
silently miss a multi-line call or a K&R signature. Each call site is then
attributed to the behavior(s) that reach it:

- Roots are the functions a behavior names via ``CALL_NATIVE`` (its init/loop).
- From each root we follow the static call graph, but only *through* object
  behavior code (functions defined in ``src/game/behaviors/``). Calls to engine
  helpers -- ``spawn_object``, ``cur_obj_play_sound_2``, ``set_mario_npc_dialog``
  -- are leaves: they are the relation vocabulary, not edges to recurse into.
- Every function reached from a root is attributed to that root's behavior(s);
  a helper reached from two behaviors is attributed to both.

The result is one ``SM64BehaviorCall`` row per (behavior, call site). The
high-value relations (spawns / sounds / dialog / model / morph / seek) are
derived from this backbone as SQL views (``behavior_calls_*`` in
``everything.py``), exactly as ``behavior_command`` feeds ``behavior_spawn``.
The raw rows -- including calls that match no relation view -- are retained so
that ``behavior_call_unclassified`` can report the uncaptured surface: the
completeness audit is a query, not a promise.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

# tree-sitter is a build-time dependency (it produces the database); it never
# ships to the web client. Pinned to 0.21.x in pyproject (its Language()/Parser()
# API differs from 0.22+).
import tree_sitter_c
from tree_sitter import Language, Parser

BEHAVIOR_SUBDIR = ("src", "game", "behaviors")

# Many behaviors dispatch their per-frame logic through an action-function table:
#   void (*sFooActions[])(void) = { foo_act_0, foo_act_1, ... };
#   void bhv_foo_loop(void) { ... cur_obj_call_action_function(sFooActions); }
# The table is invoked ONLY via this one dispatcher -- verified across the whole
# decomp: every such table is referenced exactly twice, its definition and its
# cur_obj_call_action_function argument, with no manual subscript dispatch. So
# reachability follows that call into each function the table lists; otherwise
# those per-action functions (and the spawns/sounds/dialog inside them) would be
# invisible, since the dispatch goes through a function pointer the call graph
# cannot see.
_DISPATCHERS = {"cur_obj_call_action_function"}
_FN_PTR_TABLE = re.compile(r"\(\s*\*\s*(\w+)\s*\[\s*\]\s*\)\s*\(")


@dataclass
class SM64BehaviorCall:
    behavior_name: str  # owning bhv* (joins behavior); attributed by reachability
    function: str  # the enclosing C function the call sits in
    seq: int  # 0-based position of the call within that function
    call: str  # the callee, e.g. 'spawn_object' or 'cur_obj_play_sound_2'
    args: str  # comment-stripped, comma-joined arguments ("" for none)
    args_json: str  # JSON array of the top-level arguments ("[]" for none)
    file: str  # repo-relative path of the definition (clickable provenance)
    line: int  # 1-based line of the call site


@dataclass
class _Call:
    callee: str
    args: List[str]
    line: int


@dataclass
class _Func:
    name: str
    file: str  # repo-relative
    calls: List[_Call] = field(default_factory=list)


_parser: Optional[Parser] = None


def _get_parser() -> Parser:
    global _parser
    if _parser is None:
        language = Language(tree_sitter_c.language(), "c")
        parser = Parser()
        parser.set_language(language)
        _parser = parser
    return _parser


def _function_name(node) -> Optional[str]:
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


def _collect_calls(body) -> List[_Call]:
    """Every ``call_expression`` in a function body, in source (pre-order)."""
    calls: List[_Call] = []

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
                calls.append(_Call(fn.text.decode(), args, node.start_point[0] + 1))
        for child in node.children:
            visit(child)

    visit(body)
    return calls


def _functions_from_tree(tree, rel: str) -> List[_Func]:
    funcs: List[_Func] = []

    def visit(node) -> None:
        if node.type == "function_definition":
            name = _function_name(node)
            body = node.child_by_field_name("body")
            if name is not None and body is not None:
                funcs.append(_Func(name, rel, _collect_calls(body)))
            return  # C has no nested function definitions
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return funcs


def _find_descendant(node, node_type):
    if node.type == node_type:
        return node
    for child in node.children:
        found = _find_descendant(child, node_type)
        if found is not None:
            return found
    return None


def _action_tables_from_tree(tree) -> Dict[str, List[str]]:
    """Map every ``void (*sFoo[])(void) = {...}`` table to the functions it lists.

    NULL / non-function initializer entries are kept verbatim here; the caller
    filters to functions it actually parsed, so they harmlessly drop out.
    """
    tables: Dict[str, List[str]] = {}

    def visit(node) -> None:
        if node.type == "declaration":
            match = _FN_PTR_TABLE.search(node.text.decode())
            init = _find_descendant(node, "initializer_list") if match else None
            if match and init is not None:
                fns = [
                    child.text.decode()
                    for child in init.named_children
                    if child.type == "identifier"
                ]
                if fns:
                    tables[match.group(1)] = fns
            return  # a declaration holds no nested action tables
        for child in node.children:
            visit(child)

    visit(tree.root_node)
    return tables


def parse_c_functions(path: Path, rel: str) -> List[_Func]:
    """Parse one C file into its function definitions and their call sites."""
    return _functions_from_tree(_get_parser().parse(path.read_bytes()), rel)


def _files_defining(repo: Path, names: Set[str]) -> List[Path]:
    """Find the ``.c`` files outside behaviors/ that define any of ``names``.

    A textual prefilter keeps us from parsing the whole tree -- only files that
    mention a wanted name are parsed, and only those that truly *define* one
    (a ``function_definition``, not a prototype) are returned.
    """
    behaviors = repo.joinpath(*BEHAVIOR_SUBDIR)
    result: List[Path] = []
    for path in sorted((repo / "src").rglob("*.c")):
        if behaviors in path.parents:
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        if not any(f"{name}(" in text for name in names):
            continue
        rel = path.relative_to(repo).as_posix()
        if {fn.name for fn in parse_c_functions(path, rel)} & names:
            result.append(path)
    return result


def _reachable(
    root: str,
    funcs: Dict[str, _Func],
    recursion_set: Set[str],
    action_tables: Dict[str, List[str]],
) -> Set[str]:
    """Functions reachable from ``root`` through object-behavior code.

    Recursion descends into a callee in ``recursion_set`` (the behaviors/
    functions); everything else is a leaf. A call to the action dispatcher
    ``cur_obj_call_action_function(table)`` is followed into every function the
    table lists -- the only way those per-action functions are reached, since the
    dispatch is through a function-pointer table. ``root`` itself is always
    included, even when it lives outside behaviors/ (an external CALL_NATIVE root).
    """
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
            if call.callee in _DISPATCHERS and call.args:
                for action_fn in action_tables.get(call.args[0], ()):
                    enqueue(action_fn)
    return seen


def parse_behavior_calls(
    repo: Path, root_to_behaviors: Dict[str, List[str]]
) -> List[SM64BehaviorCall]:
    """Build the behavior_call backbone from the behavior C source.

    ``root_to_behaviors`` maps each ``CALL_NATIVE`` function name to the
    behavior(s) that name it (derived from the parsed behavior command stream).
    """
    behaviors_dir = repo.joinpath(*BEHAVIOR_SUBDIR)
    if not behaviors_dir.is_dir():
        return []

    # 1. Parse object-behavior files. These functions are the recursion set: the
    #    call graph is followed only through this object code. Action-function
    #    tables are collected from the same parse so the dispatcher can be
    #    followed into them.
    funcs: Dict[str, _Func] = {}
    action_tables: Dict[str, List[str]] = {}
    for path in sorted(behaviors_dir.glob("*.inc.c")):
        rel = path.relative_to(repo).as_posix()
        tree = _get_parser().parse(path.read_bytes())
        for fn in _functions_from_tree(tree, rel):
            funcs[fn.name] = fn
        action_tables.update(_action_tables_from_tree(tree))
    recursion_set = set(funcs)

    # 2. A few CALL_NATIVE roots live outside behaviors/ (menu/cutscene/mario
    #    loops). Parse just their files so they are entry points too; we capture
    #    their direct calls but do not recurse into their file-local helpers.
    external = set(root_to_behaviors) - recursion_set
    for path in _files_defining(repo, external):
        rel = path.relative_to(repo).as_posix()
        tree = _get_parser().parse(path.read_bytes())
        action_tables.update(_action_tables_from_tree(tree))
        for fn in _functions_from_tree(tree, rel):
            if fn.name in external and fn.name not in funcs:
                funcs[fn.name] = fn

    # 3. Reachability: attribute every function reached from a root to that
    #    root's behavior(s).
    func_behaviors: Dict[str, Set[str]] = {}
    for root, behaviors in root_to_behaviors.items():
        if root not in funcs:
            continue  # engine-helper "root" with no parsed body, or a macro
        for reached in _reachable(root, funcs, recursion_set, action_tables):
            func_behaviors.setdefault(reached, set()).update(behaviors)

    # 4. Emit one row per (behavior, call site), ordered for a stable database.
    rows: List[SM64BehaviorCall] = []
    for name in sorted(func_behaviors):
        fn = funcs[name]
        for behavior in sorted(func_behaviors[name]):
            for seq, call in enumerate(fn.calls):
                rows.append(
                    SM64BehaviorCall(
                        behavior_name=behavior,
                        function=name,
                        seq=seq,
                        call=call.callee,
                        args=", ".join(call.args),
                        args_json=json.dumps(call.args),
                        file=fn.file,
                        line=call.line,
                    )
                )
    return rows
