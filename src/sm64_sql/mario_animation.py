from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import parse_c_enum


@dataclass
class SM64MarioAnimation:
    anim_name: str  # the MARIO_ANIM_* enum, e.g. MARIO_ANIM_BACKFLIP
    anim_id: int  # the animation id


def parse_mario_animations(path: Path) -> List[SM64MarioAnimation]:
    """Parse Mario's animation ids from the enum MarioAnimID in
    mario_animation_ids.h."""
    return [
        SM64MarioAnimation(anim_name=name, anim_id=value)
        for name, value in parse_c_enum(path.read_text(), "MarioAnimID")
    ]
