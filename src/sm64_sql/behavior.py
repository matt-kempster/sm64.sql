import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from sm64_sql.parse_utils import extract_macro_args

_EXTERN = re.compile(r"extern const BehaviorScript (bhv\w+)\[\]")
_DEFINITION = re.compile(r"const BehaviorScript (bhv\w+)\[\]")


@dataclass
class SM64Behavior:
    behavior_name: str  # the bhv* symbol, e.g. bhvGoomba
    obj_list: str  # the OBJ_LIST_* processing list, or "" if none/unknown


def _parse_obj_lists(behavior_data_c: Path) -> Dict[str, str]:
    """Map each behavior to the OBJ_LIST_* from its opening BEGIN() command."""
    obj_lists: Dict[str, str] = {}
    current = None
    for line in behavior_data_c.read_text().splitlines():
        line = line.strip()
        if current is None:
            match = _DEFINITION.search(line)
            if match:
                current = match.group(1)
                obj_lists[current] = ""
            continue
        if not obj_lists[current]:
            begin_args = extract_macro_args(line, "BEGIN")
            if begin_args:
                obj_lists[current] = begin_args[0]
        if line.startswith("};"):
            current = None
    return obj_lists


def parse_behaviors(behavior_data_h: Path, behavior_data_c: Path) -> List[SM64Behavior]:
    """List every behavior (from behavior_data.h) with its object list.

    The .h declares the full set of bhv* symbols; the object list comes from
    the BEGIN() at the top of each script in behavior_data.c (empty for the few
    declared-but-not-defined-here, or scripts with no BEGIN).
    """
    obj_lists = _parse_obj_lists(behavior_data_c)
    behaviors = []
    seen = set()
    for line in behavior_data_h.read_text().splitlines():
        match = _EXTERN.search(line)
        if not match:
            continue
        name = match.group(1)
        if name in seen:
            continue
        seen.add(name)
        behaviors.append(
            SM64Behavior(behavior_name=name, obj_list=obj_lists.get(name, ""))
        )
    return behaviors
