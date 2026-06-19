from dataclasses import dataclass
from typing import Optional

from sm64_sql.behavior_param import parse_behavior_param
from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64MacroObject:
    macro_name: str
    level: str
    area: int  # AREA the macro array belongs to (from levels/<lvl>/areas/<n>/), 0 if none
    yaw: int
    pos_x: int
    pos_y: int
    pos_z: int
    bhv_param: str  # per-placement behavior param (16-bit), e.g. DIALOG_089 or 0
    bhv_param_value: Optional[int]  # resolved value, or NULL if symbolic


def try_parse_macro_object(
    line: str, level_name: str, area: int = 0
) -> Optional[SM64MacroObject]:
    # The macro is spelled MACRO_OBJECT_WITH_BHV_PARAM in the decomp. It adds a
    # trailing bhvParam argument; the preset/yaw/pos arguments keep their
    # positions, so both variants are read the same way.
    has_bhv_param = line.strip().startswith("MACRO_OBJECT_WITH_BHV_PARAM")
    macro = "MACRO_OBJECT_WITH_BHV_PARAM" if has_bhv_param else "MACRO_OBJECT"
    line_parts = extract_macro_args(line, macro)
    if line_parts is None:
        return None

    expected = 6 if has_bhv_param else 5
    if len(line_parts) != expected:
        raise ValueError(
            f"Expected {expected} args in {macro}, got {len(line_parts)}: "
            f"{line.strip()}"
        )
    # MACRO_OBJECT carries no param; MACRO_OBJECT_WITH_BHV_PARAM adds it last.
    bhv_param = parse_behavior_param(line_parts[5] if has_bhv_param else "0")
    return SM64MacroObject(
        macro_name=line_parts[0],
        level=level_name,
        area=area,
        yaw=int(line_parts[1]),
        pos_x=int(line_parts[2]),
        pos_y=int(line_parts[3]),
        pos_z=int(line_parts[4]),
        bhv_param=bhv_param.raw,
        bhv_param_value=bhv_param.value,
    )
