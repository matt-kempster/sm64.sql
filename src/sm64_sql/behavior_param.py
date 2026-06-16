"""Parse SM64 behavior-parameter expressions.

Placed objects carry a behavior parameter that the game packs into the 32-bit
``oBhvParams`` field. In the source it is written as an expression built from the
``BPARAMn`` macros (``include/behavior_data.h``)::

    #define BPARAM1(x) (((x) & 0xFF) << 24)   // 1st byte, read as oBhvParams >> 24
    #define BPARAM2(x) (((x) & 0xFF) << 16)   // 2nd byte, read as oBhvParams2ndByte
    #define BPARAM3(x) (((x) & 0xFF) << 8)    // 3rd byte
    #define BPARAM4(x) (((x) & 0xFF) << 0)    // 4th byte

So ``BPARAM1(0x01) | BPARAM2(WARP_NODE_03)`` puts ``0x01`` in the top byte and the
warp-node id in the second byte. Each byte is an independent, behavior-specific
field (a dialog id, a star index, a warp node, an enemy size, ...), which is why
this module keeps the four slots separate rather than only the combined value.

``parse_behavior_param`` records three things:

* ``raw`` -- the original expression, exactly as written (e.g. ``"DIALOG_089"``
  or ``"BPARAM1(0x01) | BPARAM2(WARP_NODE_03)"``), so nothing is lost.
* ``value`` -- the resolved 32-bit integer, but only when the whole expression
  is numeric. Expressions that reference a symbolic constant (``WARP_NODE_03``,
  ``DIALOG_089``, ...) leave this ``None`` -- resolving those would require the
  scattered ``#define`` tables, which is deliberately out of scope.
* ``param1``..``param4`` -- the argument written inside each ``BPARAMn(...)``
  slot (symbolic or numeric), or ``None`` when that slot is unused.
"""

import ast
from dataclasses import dataclass
from typing import Dict, Optional

from sm64_sql.parse_utils import extract_macro_args

# BPARAMn macro -> the left bit-shift it applies (see module docstring).
_BPARAM_SHIFT = {"BPARAM1": 24, "BPARAM2": 16, "BPARAM3": 8, "BPARAM4": 0}


@dataclass
class BehaviorParam:
    raw: str  # the behavior-param expression as written in the source
    value: Optional[int]  # resolved 32-bit value, or None if it uses symbols
    param1: Optional[str]  # argument inside BPARAM1(...), or None
    param2: Optional[str]  # argument inside BPARAM2(...) (the famous 2nd byte)
    param3: Optional[str]  # argument inside BPARAM3(...), or None
    param4: Optional[str]  # argument inside BPARAM4(...), or None


class _Unresolved(Exception):
    """Raised when an expression references a non-numeric (symbolic) value."""


def _normalize(expr: str) -> str:
    """Collapse runs of whitespace so the stored ``raw`` form is canonical."""
    return " ".join(expr.split())


def _bparam_slots(expr: str) -> Dict[int, str]:
    """Return ``{n: argument}`` for each ``BPARAMn(...)`` term present in expr."""
    slots: Dict[int, str] = {}
    for name, _shift in _BPARAM_SHIFT.items():
        index = expr.find(name + "(")
        if index == -1:
            continue
        args = extract_macro_args(expr[index:], name)
        if args:
            slots[int(name[-1])] = args[0]
    return slots


def _eval(node: ast.AST) -> int:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    # ast.Num is the pre-3.8 spelling; ast.Constant is what 3.8+ produces.
    if isinstance(node, ast.Constant):
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            return node.value
        raise _Unresolved
    if isinstance(node, ast.Num):  # pragma: no cover - legacy node on old pythons
        if isinstance(node.n, int) and not isinstance(node.n, bool):
            return node.n
        raise _Unresolved
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.BitOr):
            return left | right
        if isinstance(node.op, ast.BitAnd):
            return left & right
        if isinstance(node.op, ast.BitXor):
            return left ^ right
        if isinstance(node.op, ast.LShift):
            return left << right
        if isinstance(node.op, ast.RShift):
            return left >> right
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        raise _Unresolved
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        if isinstance(node.op, ast.UAdd):
            return +_eval(node.operand)
        if isinstance(node.op, ast.Invert):
            return ~_eval(node.operand)
        raise _Unresolved
    if isinstance(node, ast.Call):
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id in _BPARAM_SHIFT
            and len(node.args) == 1
        ):
            return (_eval(node.args[0]) & 0xFF) << _BPARAM_SHIFT[func.id]
        raise _Unresolved
    # ast.Name (a symbolic constant) and anything else cannot be resolved.
    raise _Unresolved


def _evaluate(expr: str) -> Optional[int]:
    """Resolve ``expr`` to an int, or return None if it uses symbolic names."""
    try:
        tree = ast.parse(expr, mode="eval")
        return _eval(tree)
    except (_Unresolved, SyntaxError, ValueError):
        return None


def parse_behavior_param(expr: str) -> BehaviorParam:
    """Parse a behavior-parameter expression into a :class:`BehaviorParam`.

    ``expr`` is the argument as written in the macro call. An empty or missing
    expression is treated as ``"0"`` (the default the game uses).
    """
    raw = _normalize(expr) or "0"
    slots = _bparam_slots(raw)
    return BehaviorParam(
        raw=raw,
        value=_evaluate(raw),
        param1=slots.get(1),
        param2=slots.get(2),
        param3=slots.get(3),
        param4=slots.get(4),
    )
