"""Harvest the named integer constants used in behavior parameters.

Behavior-param bytes are written as symbolic constants — ``WARP_NODE_0A``,
``STAR_INDEX_ACT_1``, ``GOOMBA_SIZE_HUGE`` — rather than numbers. This builds a
``constant`` reference table (``name`` -> ``value``) so those symbols resolve to
their integer value, and so a query can join a param byte to its meaning::

    SELECT o.behavior, c.value AS warp_node
    FROM object o JOIN constant c ON o.bhv_param_2 = c.name;

Two sources cover the constants that appear in params:

* ``enum WarpNodes`` (src/game/level_update.h) -- the ``WARP_NODE_*`` ids, by far
  the most common param symbol.
* ``include/object_constants.h`` -- ``STAR_INDEX_*``, ``GOOMBA_SIZE_*``,
  ``*_BP_*`` enemy/formation params, and the rest of the object constants.

``DIALOG_*`` params already resolve via the ``dialog`` table, so they are not
duplicated here.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import parse_c_defines, parse_c_enum


@dataclass
class SM64Constant:
    name: str  # the #define / enum name, e.g. WARP_NODE_0A or STAR_INDEX_ACT_1
    value: int  # its resolved integer value
    source: str  # where it came from: "warp_nodes" or "object_constants"


def parse_constants(
    object_constants_path: Path, level_update_path: Path
) -> List[SM64Constant]:
    constants: List[SM64Constant] = []
    seen = set()

    def add(name: str, value: int, source: str) -> None:
        if name not in seen:
            seen.add(name)
            constants.append(SM64Constant(name=name, value=value, source=source))

    if level_update_path.is_file():
        for name, value in parse_c_enum(level_update_path.read_text(), "WarpNodes"):
            add(name, value, "warp_nodes")

    if object_constants_path.is_file():
        for name, value in parse_c_defines(object_constants_path.read_text()):
            add(name, value, "object_constants")

    return constants
