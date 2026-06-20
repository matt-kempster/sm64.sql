"""Extract Mario's action state machine from ``src/game/``.

Mario is a state machine: at any moment he is in one *action* (``ACT_WALKING``,
``ACT_LONG_JUMP``, ...) and a frame of that action can transition him to another
by calling ``set_mario_action(m, ACT_*, arg)`` (or one of a few sibling setters).
The action constants and their bit-packed group/flags are declared in
``include/sm64.h``; each action runs a handler ``act_*`` selected by a ``switch``
in the per-group dispatcher ``mario_execute_*_action``; and the transitions live,
unnamed, inside those handlers and the helpers they call. This mines all three:

- **Nodes** -- every ``ACT_*`` constant, with its group and flags decoded from the
  numeric value (the masks/groups/flags themselves are not actions and are
  skipped). The handler ``act_*`` is read from the dispatcher ``switch``, which is
  authoritative: it handles shared handlers and fall-through cases that a
  name-convention guess would miss.
- **Edges** -- ``mario_action_call`` is the backbone: from each action's handler
  we follow the static call graph (via the shared ``reachable`` walk) through
  Mario's action code, and every call to a transition *setter* is recorded,
  attributed to the action(s) that reach it. The setters that take the
  destination as an argument are leaves (the relation vocabulary); the
  fixed-target helpers (``set_steep_jump_action`` -> ``ACT_STEEP_JUMP`` etc.) are
  recursed into, so the literal ``set_mario_action(ACT_*)`` inside their bodies
  produces the edge with no special-casing.

The resolved edges (``mario_transition``) and the audit residue
(``mario_action_call_unclassified`` -- setter calls whose target is a computed or
forwarded value we cannot pin to a literal action) are SQL views over the
backbone, exactly as ``behavior_call`` feeds ``behavior_calls_*``.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from sm64_sql.c_parse import (
    Func,
    collect_calls,
    find_descendant,
    function_name,
    functions_from_tree,
    parse_tree,
    reachable,
)

# The action state machine lives in mario.c (the setters + shared helpers) and
# the seven per-group action files (the handlers + their dispatchers).
MARIO_SUBDIR = ("src", "game")
MARIO_FILES = (
    "mario.c",
    "mario_actions_stationary.c",
    "mario_actions_moving.c",
    "mario_actions_airborne.c",
    "mario_actions_submerged.c",
    "mario_actions_cutscene.c",
    "mario_actions_automatic.c",
    "mario_actions_object.c",
)

# Setters that take the destination action as an explicit argument (index 1 --
# after the MarioState* receiver). These are the leaf transition vocabulary:
# reachability does not recurse into them, the edge is read from the call site.
TRANSITION_SETTERS = frozenset(
    {
        "set_mario_action",
        "drop_and_set_mario_action",
        "hurt_and_set_mario_action",
        "set_jumping_action",
    }
)
# set_mario_action dispatches through these per-group helpers; they (and the
# public setters above) are kept out of the recursion set so the engine-internal
# landing remaps inside them are not misattributed to every calling action.
_SETTER_INTERNALS = frozenset(
    {
        "set_mario_action_airborne",
        "set_mario_action_moving",
        "set_mario_action_submerged",
        "set_mario_action_cutscene",
    }
)
_ACTION_ARG = 1  # set_mario_action(m, ACT_*, ...) -- the action is the 2nd arg
_ACT_LITERAL = re.compile(r"\bACT_[A-Z0-9_]+\b")  # a literal action in an expression

# include/sm64.h declarations. An action is "#define ACT_X 0x........"; the
# masks/groups/flags use a different shape (a (1<<n) / (n<<6) expression, or a
# name ending in _MASK) and are filtered out as non-actions.
_ACT_DEF = re.compile(r"^#define\s+(ACT_\w+)\s+(0x[0-9A-Fa-f]+)\b", re.MULTILINE)
_FLAG_DEF = re.compile(
    r"#define\s+ACT_FLAG_(\w+)\s+(?:/\*.*?\*/\s*)?\(1\s*<<\s*(\d+)\)"
)
_GROUP_DEF = re.compile(
    r"#define\s+ACT_GROUP_(\w+)\s+(?:/\*.*?\*/\s*)?\((\d+)\s*<<\s*6\)"
)
_ACT_GROUP_MASK = 0x1C0


@dataclass
class SM64MarioAction:
    """One Mario action: a node in the state machine."""

    action_name: str  # ACT_* (joins as the key)
    id: str  # the 32-bit value, e.g. 0x0C400201
    group_name: Optional[str]  # STATIONARY / MOVING / ... / OBJECT, from the bits
    flags_json: str  # JSON array of the ACT_FLAG_* names set in the value
    handler: Optional[str]  # the act_* function the dispatcher runs (else NULL)
    file: Optional[str]  # repo-relative file the handler is defined in
    line: Optional[int]  # 1-based line of the handler definition


@dataclass
class SM64MarioActionCall:
    """One transition-setter call, attributed to a source action by reachability.

    ``target`` is the raw action argument: a literal ``ACT_*`` for a resolved
    edge (see the mario_transition view), or a computed / forwarded expression
    that stays in the audit residue (mario_action_call_unclassified)."""

    action_name: str  # source ACT_* (joins mario_action), via reachability
    function: str  # the C function the call sits in
    seq: int  # 0-based position of the call within that function
    call: str  # the setter, e.g. set_mario_action
    target: Optional[str]  # the action argument (ACT_* literal, or an expression)
    args: str  # comment-stripped, comma-joined arguments
    args_json: str  # JSON array of the top-level arguments
    file: str  # repo-relative path of the definition (clickable provenance)
    line: int  # 1-based line of the call site


@dataclass
class SM64MarioActionDataTransition:
    """A transition whose destination is a runtime value, resolved to a literal
    action (what the literal-only mario_transition view cannot see):

    - a forwarded parameter: a helper does ``set_mario_action(m, landAction)`` and
      a caller passes a literal (e.g. ``common_air_action_step(m, ACT_JUMP_LAND)``)
      -- resolved one level, per-caller, so it is attributed only to the actions
      that reach that caller;
    - a literal embedded in an expression: a ternary
      ``cond ? ACT_DIVE : ACT_JUMP_KICK`` -- both branches are real transitions.

    Struct-table landings (``landingAction->endAction``) and computed targets stay
    unresolved in mario_action_call_unclassified."""

    action_name: str  # source ACT_* (joins mario_action), via reachability
    to_action: str  # the resolved destination ACT_* (joins mario_action)
    source: str  # "expr" (literal in expression) or the forwarded parameter name
    function: str  # the C function the transition was resolved at
    file: str
    line: int


@dataclass
class ParsedMarioActions:
    actions: List[SM64MarioAction]
    calls: List[SM64MarioActionCall]
    data_transitions: List[SM64MarioActionDataTransition]


def _parse_action_constants(
    header: str,
) -> Tuple[List[Tuple[str, int]], Dict[int, str], List[Tuple[str, int]]]:
    """Read include/sm64.h into (actions, group_by_value, flag_bits).

    actions: (name, value) for every real ACT_* constant.
    group_by_value: (value & ACT_GROUP_MASK) -> group name (STATIONARY, ...).
    flag_bits: (flag name, bit) for every ACT_FLAG_*, sorted by bit.
    """
    group_by_value = {int(v) << 6: name for name, v in _GROUP_DEF.findall(header)}
    flag_bits = sorted(
        ((name, int(bit)) for name, bit in _FLAG_DEF.findall(header)),
        key=lambda nb: nb[1],
    )
    actions: List[Tuple[str, int]] = []
    for name, value in _ACT_DEF.findall(header):
        if name.endswith("_MASK") or name.startswith(("ACT_FLAG_", "ACT_GROUP_")):
            continue
        actions.append((name, int(value, 16)))
    return actions, group_by_value, flag_bits


def _action_nodes(
    actions: List[Tuple[str, int]],
    group_by_value: Dict[int, str],
    flag_bits: List[Tuple[str, int]],
    handlers: Dict[str, str],
    funcs: Dict[str, Func],
) -> List[SM64MarioAction]:
    nodes: List[SM64MarioAction] = []
    for name, value in actions:
        group = group_by_value.get(value & _ACT_GROUP_MASK) if value else None
        flags = [flag for flag, bit in flag_bits if value & (1 << bit)]
        handler = handlers.get(name)
        fn = funcs.get(handler) if handler else None
        nodes.append(
            SM64MarioAction(
                action_name=name,
                id=f"0x{value:08X}",
                group_name=group,
                flags_json=json.dumps(flags),
                handler=handler,
                file=fn.file if fn else None,
                line=fn.line if fn else None,
            )
        )
    return sorted(nodes, key=lambda a: a.id)


def _handlers_from_switch(node, handlers: Dict[str, str]) -> None:
    """Fill ACT_* -> act_* from a mario_execute_*_action dispatcher switch.

    A bare ``case ACT_X:`` with no body falls through to the next case's handler,
    so labels are accumulated until a case that actually calls an ``act_*``.
    """
    switch = find_descendant(node, "switch_statement")
    body = switch.child_by_field_name("body") if switch is not None else None
    if body is None:
        return
    pending: List[str] = []
    for case in body.named_children:
        if case.type != "case_statement":
            continue
        value = case.child_by_field_name("value")
        if value is None:  # default:
            pending = []
            continue
        label = value.text.decode()
        has_body = len([c for c in case.named_children if c.type != "comment"]) > 1
        if not has_body:
            pending.append(label)  # fall-through to the next case
            continue
        handler = next(
            (c.callee for c in collect_calls(case) if c.callee.startswith("act_")),
            None,
        )
        if handler is not None:
            for lbl in pending:
                handlers[lbl] = handler
            handlers[label] = handler
        pending = []


def _dispatch_handlers(trees: List) -> Dict[str, str]:
    handlers: Dict[str, str] = {}

    def visit(node) -> None:
        if node.type == "function_definition":
            name = function_name(node)
            if name and name.startswith("mario_execute_") and name.endswith("_action"):
                _handlers_from_switch(node, handlers)
            return  # C has no nested function definitions
        for child in node.children:
            visit(child)

    for tree in trees:
        visit(tree.root_node)
    return handlers


def _resolve_data_transitions(
    funcs: Dict[str, Func],
    func_actions: Dict[str, Set[str]],
    action_names: Set[str],
    literal_edges: Set[Tuple[str, str]],
) -> List[SM64MarioActionDataTransition]:
    """Resolve transitions whose target is a runtime value, beyond the literals.

    Two shapes, both attributed only to actions that actually reach the code so
    nothing is over-attributed, and both excluding edges already visible as
    literals (``literal_edges``):
      - a literal embedded in the target expression (a ternary's branches);
      - the target is a parameter of the enclosing helper, resolved one level
        from the helper's call sites (a forwarded literal land action).
    """
    callers: Dict[str, List[Tuple[str, List[str], int]]] = {}
    for fn in funcs.values():
        for call in fn.calls:
            callers.setdefault(call.callee, []).append((fn.name, call.args, call.line))

    rows: List[SM64MarioActionDataTransition] = []
    seen: Set[Tuple[str, str]] = set()

    def emit(
        action: str, to_action: str, source: str, function: str, file: str, line: int
    ) -> None:
        if to_action not in action_names:
            return
        key = (action, to_action)
        if key in literal_edges or key in seen:
            return
        seen.add(key)
        rows.append(
            SM64MarioActionDataTransition(
                action, to_action, source, function, file, line
            )
        )

    for name in sorted(func_actions):
        fn = funcs[name]
        for call in fn.calls:
            if call.callee not in TRANSITION_SETTERS:
                continue
            tgt = call.args[_ACTION_ARG] if len(call.args) > _ACTION_ARG else None
            if tgt is None or tgt in action_names:
                continue  # no target, or already a clean literal edge
            lits = [lit for lit in _ACT_LITERAL.findall(tgt) if lit in action_names]
            if lits:
                # A literal embedded in an expression (a ternary's branches);
                # provenance is the setter call site itself.
                for lit in lits:
                    for action in sorted(func_actions[name]):
                        emit(action, lit, "expr", fn.name, fn.file, call.line)
            elif tgt in fn.params:
                # A forwarded parameter: resolve from the helper's call sites,
                # attributing to the actions that reach each caller. Provenance is
                # the caller's call site, where the literal action is written.
                idx = fn.params.index(tgt)
                for caller, cargs, cline in callers.get(fn.name, ()):
                    if idx >= len(cargs) or cargs[idx] not in action_names:
                        continue
                    cfile = funcs[caller].file if caller in funcs else fn.file
                    for action in sorted(func_actions.get(caller, ())):
                        emit(action, cargs[idx], tgt, caller, cfile, cline)
    return sorted(rows, key=lambda r: (r.action_name, r.to_action))


def parse_mario_actions(repo: Path) -> ParsedMarioActions:
    """Build the mario_action nodes and the mario_action_call edge backbone."""
    header_file = repo / "include" / "sm64.h"
    game_dir = repo.joinpath(*MARIO_SUBDIR)
    if not header_file.is_file() or not game_dir.is_dir():
        return ParsedMarioActions([], [], [])

    actions, group_by_value, flag_bits = _parse_action_constants(
        header_file.read_text()
    )
    action_names = {name for name, _ in actions}

    # Parse mario.c + the per-group action files into one function table and keep
    # their trees for the dispatcher-switch walk.
    funcs: Dict[str, Func] = {}
    trees = []
    for filename in MARIO_FILES:
        path = game_dir / filename
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        # Strip preprocessor conditionals so brace-splitting #if ENABLE_RUMBLE
        # blocks don't drop handlers like act_lava_boost / act_start_sleeping.
        tree = parse_tree(path, strip_conditionals=True)
        trees.append(tree)
        for fn in functions_from_tree(tree, rel):
            funcs[fn.name] = fn

    handlers = _dispatch_handlers(trees)
    nodes = _action_nodes(actions, group_by_value, flag_bits, handlers, funcs)

    # Reachability: from each action's handler, follow the call graph through
    # Mario's action code (everything except the setter leaves), attributing every
    # reached function to that action. A helper shared by many actions is
    # attributed to all of them -- those are all real possible transitions.
    recursion_set = {
        name
        for name in funcs
        if name not in TRANSITION_SETTERS and name not in _SETTER_INTERNALS
    }
    func_actions: Dict[str, Set[str]] = {}
    for action, handler in handlers.items():
        if action not in action_names or handler not in funcs:
            continue
        for reached in reachable(handler, funcs, recursion_set):
            func_actions.setdefault(reached, set()).add(action)

    # Emit one row per (action, transition-setter call site), stably ordered,
    # and collect the literal-at-site edges (so the data resolver below only adds
    # transitions the literal mario_transition view cannot already see).
    calls: List[SM64MarioActionCall] = []
    literal_edges: Set[Tuple[str, str]] = set()
    for name in sorted(func_actions):
        fn = funcs[name]
        for action in sorted(func_actions[name]):
            for seq, call in enumerate(fn.calls):
                if call.callee not in TRANSITION_SETTERS:
                    continue
                target = (
                    call.args[_ACTION_ARG] if len(call.args) > _ACTION_ARG else None
                )
                if target in action_names:
                    literal_edges.add((action, target))
                calls.append(
                    SM64MarioActionCall(
                        action_name=action,
                        function=name,
                        seq=seq,
                        call=call.callee,
                        target=target,
                        args=", ".join(call.args),
                        args_json=json.dumps(call.args),
                        file=fn.file,
                        line=call.line,
                    )
                )

    data_transitions = _resolve_data_transitions(
        funcs, func_actions, action_names, literal_edges
    )
    return ParsedMarioActions(nodes, calls, data_transitions)
