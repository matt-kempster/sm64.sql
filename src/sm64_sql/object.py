from dataclasses import dataclass
from typing import List, Optional

from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64Object:
    model_name: str
    level: str
    initial_x: int
    initial_y: int
    initial_z: int
    initial_rot_x: int
    initial_rot_y: int
    initial_rot_z: int
    # TODO: Figure out how to parse this
    # beh_param: int
    behavior: str
    in_act_1: bool
    in_act_2: bool
    in_act_3: bool
    in_act_4: bool
    in_act_5: bool
    in_act_6: bool


def parse_acts(acts: str) -> List[bool]:
    """Parse an OBJECT_WITH_ACTS act mask like ``ACT_1 | ACT_3`` into 6 flags."""
    if acts == "ALL_ACTS":
        return [True] * 6
    act_presence = [False] * 6
    for act_id in acts.split("|"):
        act = int(act_id.strip()[len("ACT_") :])
        act_presence[act - 1] = True
    return act_presence


def try_parse_object(line: str, level: str) -> Optional[SM64Object]:
    has_acts = line.strip().startswith("OBJECT_WITH_ACTS")
    macro_name = "OBJECT_WITH_ACTS" if has_acts else "OBJECT"
    line_parts = extract_macro_args(line, macro_name)
    if line_parts is None:
        return None

    expected = 10 if has_acts else 9
    if len(line_parts) != expected:
        raise ValueError(
            f"Expected {expected} args in {macro_name}, got {len(line_parts)}: "
            f"{line.strip()}"
        )

    # If ACT_* not present, the object is in all the acts
    act_presence = parse_acts(line_parts[9]) if has_acts else [True] * 6

    return SM64Object(
        level=level,
        model_name=line_parts[0],
        initial_x=int(line_parts[1]),
        initial_y=int(line_parts[2]),
        initial_z=int(line_parts[3]),
        initial_rot_x=int(line_parts[4]),
        initial_rot_y=int(line_parts[5]),
        initial_rot_z=int(line_parts[6]),
        # TODO: Figure out how to parse this
        # beh_param=int(line_parts[7], 16),
        behavior=line_parts[8],
        in_act_1=act_presence[0],
        in_act_2=act_presence[1],
        in_act_3=act_presence[2],
        in_act_4=act_presence[3],
        in_act_5=act_presence[4],
        in_act_6=act_presence[5],
    )
