from dataclasses import dataclass
from typing import Optional

from parse_utils import strip_comments_and_whitespace


@dataclass
class SM64MacroObject:
    macro_name: str
    level: str
    yaw: int
    pos_x: int
    pos_y: int
    pos_z: int


def try_parse_macro_object(line: str, level_name: str) -> Optional[SM64MacroObject]:
    if not line.startswith("MACRO_OBJECT") or line.startswith("MACRO_OBJECT_END"):
        return None
    has_beh_param = False
    if line.startswith("MACRO_OBJECT_WITH_BEH_PARAM"):
        has_beh_param = True
        line = line.replace("MACRO_OBJECT_WITH_BEH_PARAM(", "").replace("),", "")
    else:
        line = line.replace("MACRO_OBJECT(", "").replace("),", "")
    line_parts = [strip_comments_and_whitespace(part) for part in line.split(",")]
    if len(line_parts) != (6 if has_beh_param else 5):
        raise ValueError(f"Invalid number of parts ({len(line_parts)}) in line: {line}")
    return SM64MacroObject(
        macro_name=line_parts[0],
        level=level_name,
        yaw=int(line_parts[1]),
        pos_x=int(line_parts[2]),
        pos_y=int(line_parts[3]),
        pos_z=int(line_parts[4]),
        # TODO: beh param
    )
