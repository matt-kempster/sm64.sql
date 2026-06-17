"""Parse each behavior script in ``data/behavior_data.c`` into its commands.

A behavior is a little bytecode program written as an array of command macros::

    const BehaviorScript bhvGoomba[] = {
        BEGIN(OBJ_LIST_PUSHABLE),
        OR_INT(oFlags, (OBJ_FLAG_COMPUTE_ANGLE_TO_MARIO | ...)),
        LOAD_ANIMATIONS(oAnimations, goomba_seg8_anims_0801DA4C),
        CALL_NATIVE(bhv_goomba_init),
        BEGIN_LOOP(),
            CALL_NATIVE(bhv_goomba_update),
        END_LOOP(),
    };

This records one row per command, in order (``seq``), keeping both the
comma-joined argument text (readable) and a JSON array of the top-level-split
arguments. The arguments are split here, once, with the bracket-aware splitter
so that expressions like ``(OBJ_FLAG_A | OBJ_FLAG_B)`` stay a single argument.

The high-value relations between behaviors — what each spawns, the native C
functions it calls, the animations/collision it loads — are derived from this
backbone as SQL *views* (see ``ENTITY_VIEWS`` in ``everything.py``) which read
the JSON with ``json_extract``. The raw ``args_json`` column is also what makes
a "this symbol appears in any argument position" query possible via
``json_each`` — the door left open for ad-hoc questions the views do not cover.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sm64_sql.parse_utils import extract_call

_DEFINITION = re.compile(r"const BehaviorScript (bhv\w+)\[\]")


@dataclass
class SM64BehaviorCommand:
    behavior_name: str  # the bhv* script this command belongs to (joins behavior)
    seq: int  # 0-based position within the script; preserves command order
    command: str  # the opcode macro, e.g. CALL_NATIVE, SPAWN_CHILD, BEGIN_LOOP
    args: str  # the arguments, comment-stripped and comma-joined ("" for none)
    args_json: str  # JSON array of the top-level-split arguments ("[]" for none)


def parse_behavior_commands(behavior_data_c: Path) -> List[SM64BehaviorCommand]:
    """Read every ``bhv*[]`` script body into an ordered list of commands."""
    commands: List[SM64BehaviorCommand] = []
    current: Optional[str] = None
    seq = 0
    for raw in behavior_data_c.read_text().splitlines():
        line = raw.strip()
        if current is None:
            match = _DEFINITION.search(line)
            if match:
                current = match.group(1)
                seq = 0
            continue
        if line.startswith("};"):
            current = None
            continue
        call = extract_call(line)
        if call is None:
            continue
        name, parsed_args = call
        commands.append(
            SM64BehaviorCommand(
                behavior_name=current,
                seq=seq,
                command=name,
                args=", ".join(parsed_args),
                args_json=json.dumps(parsed_args),
            )
        )
        seq += 1
    return commands
