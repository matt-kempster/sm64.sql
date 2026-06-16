from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64Warp:
    level: str  # source level folder
    area: int  # source area index, or 0 for a level-global warp (outside any AREA)
    node_id: str  # WARP_NODE_* id of this node
    dest_level: str  # destination LEVEL_* (joins to level.level_name)
    dest_area: int  # destination area index
    dest_node: str  # WARP_NODE_* id arrived at in the destination
    flags: str  # e.g. WARP_NO_CHECKPOINT
    is_painting: bool  # PAINTING_WARP_NODE vs ordinary WARP_NODE


@dataclass
class SM64InstantWarp:
    level: str  # source level folder
    area: int  # source area index
    warp_index: int  # INSTANT_WARP index
    dest_area: int  # area teleported to (within the same level)
    displace_x: int
    displace_y: int
    displace_z: int


def parse_warps(path: Path, level: str) -> Tuple[List[SM64Warp], List[SM64InstantWarp]]:
    """Parse warp commands from a level script.c, tracking the AREA context."""
    warps: List[SM64Warp] = []
    instant_warps: List[SM64InstantWarp] = []
    area = 0
    for line in path.read_text().splitlines():
        line = line.strip()

        area_args = extract_macro_args(line, "AREA")
        if area_args is not None:
            try:
                area = int(area_args[0])
            except ValueError:
                area = 0
            continue
        if line.startswith("END_AREA"):
            area = 0
            continue

        matched = False
        for macro, is_painting in (("WARP_NODE", False), ("PAINTING_WARP_NODE", True)):
            args = extract_macro_args(line, macro)
            if args is None:
                continue
            if len(args) != 5:
                raise ValueError(f"Expected 5 args in {macro}: {line}")
            warps.append(
                SM64Warp(
                    level=level,
                    area=area,
                    node_id=args[0],
                    dest_level=args[1],
                    dest_area=int(args[2]),
                    dest_node=args[3],
                    flags=args[4],
                    is_painting=is_painting,
                )
            )
            matched = True
            break
        if matched:
            continue

        instant_args = extract_macro_args(line, "INSTANT_WARP")
        if instant_args is not None:
            if len(instant_args) != 5:
                raise ValueError(f"Expected 5 args in INSTANT_WARP: {line}")
            instant_warps.append(
                SM64InstantWarp(
                    level=level,
                    area=area,
                    warp_index=int(instant_args[0]),
                    dest_area=int(instant_args[1]),
                    displace_x=int(instant_args[2]),
                    displace_y=int(instant_args[3]),
                    displace_z=int(instant_args[4]),
                )
            )
    return warps, instant_warps
