import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sm64_sql.parse_utils import (
    extract_macro_args,
    split_top_level,
    strip_block_comments,
)

# The per-level camera-trigger tables and the level<->table map both live in the
# decomp at fixed paths.
CAMERA_C = ("src", "game", "camera.c")
LEVEL_DEFINES = ("levels", "level_defines.h")

# A data table is `struct CameraTrigger sCamFoo[] = {`. The master dispatch array
# is `struct CameraTrigger *sCameraTriggers[...]` -- the leading `*` keeps it from
# matching here, and we guard its name explicitly as well.
_TABLE_START = re.compile(r"struct CameraTrigger (sCam[A-Za-z0-9_]+)\[\]\s*=")
_MASTER_ARRAY = "sCameraTriggers"


@dataclass
class SM64CameraTrigger:
    """One row of a ``struct CameraTrigger sCam*[]`` table in camera.c.

    Each trigger is a world-space bounding box; while Mario is inside it the
    ``event`` function runs, adjusting the camera. The box is centred at
    (``center_x``, ``center_y``, ``center_z``) with half-extents
    (``bounds_x``, ``bounds_y``, ``bounds_z``) and is rotated about the vertical
    axis by ``bounds_yaw`` (an s16 angle, 0x10000 == 360 degrees).
    """

    level: Optional[str]  # levels/<folder> the table is wired to, or None if unused
    camera_table: str  # the sCam* array symbol, e.g. sCamBOB
    seq: int  # 0-based index of the row within its table
    area: int  # area this applies in, or -1 for a whole-level default
    event: str  # the CameraEvent function called while Mario is inside the box
    center_x: int
    center_y: int
    center_z: int
    bounds_x: int  # half-extent from the centre along each axis
    bounds_y: int
    bounds_z: int
    bounds_yaw: int  # s16 angle rotating the box about the vertical (Y) axis
    doc: Optional[str]  # the doc comment above the table, if any
    file: str
    line: int


def _camera_table_to_folder(level_defines: Path) -> Dict[str, str]:
    """Map each camera-table symbol to the level folder that wires it in.

    ``DEFINE_LEVEL(name, levelEnum, courseEnum, folder, ..., cameratable)`` has
    the folder as arg 4 and the camera table as its last arg (``_`` for none).
    The master ``sCameraTriggers`` array is built from exactly these macros, so a
    table absent here (e.g. the defined-but-unused ``sCamBOB``) is dead code.
    """
    mapping: Dict[str, str] = {}
    for line in level_defines.read_text().splitlines():
        args = extract_macro_args(line, "DEFINE_LEVEL")
        if args is None or len(args) < 5:
            continue
        folder = args[3]
        camera_table = args[-1]
        if camera_table and camera_table != "_":
            mapping[camera_table] = folder
    return mapping


def _doc_above(lines: List[str], idx: int) -> Optional[str]:
    """Return the contiguous comment block immediately above ``lines[idx]``."""
    collected: List[str] = []
    j = idx - 1
    while j >= 0:
        stripped = lines[j].strip()
        if stripped == "":
            break
        is_comment = (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.endswith("*/")
        )
        if not is_comment:
            break
        collected.append(stripped)
        if stripped.startswith("/*"):  # reached the top of a block comment
            break
        j -= 1
    cleaned: List[str] = []
    for stripped in reversed(collected):
        text = stripped.lstrip("/").lstrip("*").strip()
        text = text.rstrip("/").rstrip("*").strip()
        if text:
            cleaned.append(text)
    joined = " ".join(cleaned).strip()
    return joined or None


def _parse_row(content: str) -> Optional[Tuple[int, str, List[int]]]:
    """Parse the inside of one ``{ area, event, x, y, z, ... }`` row."""
    parts = [p.strip() for p in split_top_level(content, ",")]
    if len(parts) != 9:
        return None
    try:
        area = int(parts[0], 0)
        nums = [int(p, 0) for p in parts[2:]]
    except ValueError:
        return None
    return area, parts[1], nums


def parse_camera_triggers(repo: Path) -> List[SM64CameraTrigger]:
    """Parse every ``struct CameraTrigger sCam*[]`` table from camera.c.

    Every defined table is captured (the backbone); each is resolved to the level
    folder that wires it via ``level_defines.h``. A table no level references
    (``sCamBOB``) yields rows with ``level = None`` -- surfaced, not dropped.
    """
    camera_c = repo.joinpath(*CAMERA_C)
    if not camera_c.is_file():
        return []
    level_defines = repo.joinpath(*LEVEL_DEFINES)
    table_to_folder = (
        _camera_table_to_folder(level_defines) if level_defines.is_file() else {}
    )
    rel = camera_c.relative_to(repo).as_posix()
    lines = camera_c.read_text().splitlines()

    triggers: List[SM64CameraTrigger] = []
    i = 0
    while i < len(lines):
        match = _TABLE_START.match(lines[i].strip())
        if not match or match.group(1) == _MASTER_ARRAY:
            i += 1
            continue
        table = match.group(1)
        doc = _doc_above(lines, i)
        folder = table_to_folder.get(table)  # None if the table is unused
        seq = 0
        j = i + 1
        while j < len(lines):
            stripped = strip_block_comments(lines[j]).split("//")[0].strip()
            if stripped.startswith("}") and not stripped.startswith("{"):
                break
            if "NULL_TRIGGER" in stripped:
                j += 1
                continue
            if stripped.startswith("{") and "}" in stripped:
                inner = stripped[stripped.index("{") + 1 : stripped.rindex("}")]
                row = _parse_row(inner)
                if row is not None:
                    area, event, nums = row
                    triggers.append(
                        SM64CameraTrigger(
                            level=folder,
                            camera_table=table,
                            seq=seq,
                            area=area,
                            event=event,
                            center_x=nums[0],
                            center_y=nums[1],
                            center_z=nums[2],
                            bounds_x=nums[3],
                            bounds_y=nums[4],
                            bounds_z=nums[5],
                            bounds_yaw=nums[6],
                            doc=doc,
                            file=rel,
                            line=j + 1,
                        )
                    )
                    seq += 1
            j += 1
        i = j + 1
    return triggers
