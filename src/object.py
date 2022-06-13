from dataclasses import dataclass
from typing import Optional, List

from parse_utils import strip_comments_and_whitespace


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


def try_parse_object(line: str, level: str) -> Optional[SM64Object]:
    if not line.startswith("OBJECT"):
        return None

    def parse_acts(acts: str) -> List[bool]:
        if acts == "ALL_ACTS":
            return [True for _ in range(6)]
        act_presence = [False for _ in range(6)]
        for act_id in acts.split(" | "):
            act = int(act_id[len("ACT_") :])
            act_presence[act - 1] = True
        return act_presence

    has_acts = False
    if line.startswith("OBJECT_WITH_ACTS"):
        has_acts = True
        line = line.replace("OBJECT_WITH_ACTS(", "").replace("),", "")
    else:
        line = line.replace("OBJECT(", "").replace("),", "")
    line_parts = [strip_comments_and_whitespace(part) for part in line.split(",")]
    if len(line_parts) != (10 if has_acts else 9):
        raise ValueError(f"Invalid number of parts ({len(line_parts)}) in line: {line}")

    # If ACT_* not present, the object is in all the acts
    act_presence = parse_acts(line_parts[9]) if has_acts else [True for _ in range(6)]

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
