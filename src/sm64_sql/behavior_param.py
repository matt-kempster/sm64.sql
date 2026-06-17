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

from dataclasses import dataclass
from typing import Dict, Optional

from sm64_sql.parse_utils import evaluate_int, extract_macro_args

# BPARAMn macro -> the left bit-shift it applies (see module docstring).
_BPARAM_SHIFT = {"BPARAM1": 24, "BPARAM2": 16, "BPARAM3": 8, "BPARAM4": 0}

# BPARAMn as callable macros for the shared integer evaluator: each masks its
# argument to a byte and shifts it into place.
_BPARAM_FUNCS = {
    name: (lambda shift: lambda value: (value & 0xFF) << shift)(shift)
    for name, shift in _BPARAM_SHIFT.items()
}


@dataclass
class BehaviorParam:
    raw: str  # the behavior-param expression as written in the source
    value: Optional[int]  # resolved 32-bit value, or None if it uses symbols
    param1: Optional[str]  # argument inside BPARAM1(...), or None
    param2: Optional[str]  # argument inside BPARAM2(...) (the famous 2nd byte)
    param3: Optional[str]  # argument inside BPARAM3(...), or None
    param4: Optional[str]  # argument inside BPARAM4(...), or None


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


def parse_behavior_param(expr: str) -> BehaviorParam:
    """Parse a behavior-parameter expression into a :class:`BehaviorParam`.

    ``expr`` is the argument as written in the macro call. An empty or missing
    expression is treated as ``"0"`` (the default the game uses). The value is
    resolved only when the whole expression is numeric (the ``BPARAMn`` packers
    are known to the evaluator); a symbolic constant leaves ``value`` None.
    """
    raw = _normalize(expr) or "0"
    slots = _bparam_slots(raw)
    return BehaviorParam(
        raw=raw,
        value=evaluate_int(raw, functions=_BPARAM_FUNCS),
        param1=slots.get(1),
        param2=slots.get(2),
        param3=slots.get(3),
        param4=slots.get(4),
    )
