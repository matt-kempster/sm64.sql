from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from sm64_sql.parse_utils import (
    extract_macro_args,
    parse_c_enum,
    split_top_level,
    strip_comments,
)

# Try the more specific macro names first; extract_macro_args only matches an
# exact `name(` anyway, but this keeps the intent obvious.
_SPECIAL_OBJECT_MACROS = (
    "SPECIAL_OBJECT_WITH_YAW_AND_PARAM",
    "SPECIAL_OBJECT_WITH_YAW",
    "SPECIAL_OBJECT",
)


@dataclass
class SM64SpecialPreset:
    preset_name: str  # the special_* enum, e.g. special_wooden_door
    preset_id: int  # numeric id from enum SpecialPresets
    preset_type: str  # SPTYPE_* size/param category
    default_param: int  # default behavior param (used by SPTYPE_DEF_PARAM_AND_YROT)
    model_name: str  # MODEL_* (joins to model.model_name)
    behavior: str  # bhv* behavior symbol, or NULL


@dataclass
class SM64SpecialObject:
    preset_name: str  # as written in the source (may be an enum alias)
    preset_id: int  # resolved id; joins to special_preset.preset_id (-1 if unknown)
    level: str  # level folder
    area: int  # area number within the level
    pos_x: int
    pos_y: int
    pos_z: int
    yaw: int  # 0 when the placement macro carries no yaw


def parse_special_presets(data_path: Path, names_path: Path) -> List[SM64SpecialPreset]:
    """Parse the sSpecialObjectPresets[] array in special_presets.inc.c.

    Each row already names its preset, so it pairs with the numeric id from
    enum SpecialPresets by name rather than by position.
    """
    ids = dict(parse_c_enum(names_path.read_text(), "SpecialPresets"))
    presets = []
    within = False
    for line in data_path.read_text().splitlines():
        line = strip_comments(line)
        if not within:
            if "SpecialObjectPresets[]" in line and "{" in line:
                within = True
            continue
        if line.startswith("};"):
            break
        if "{" not in line or "}" not in line:
            continue
        inner = line[line.index("{") + 1 : line.rindex("}")]
        parts = [part.strip() for part in split_top_level(inner, ",")]
        if len(parts) != 5:
            raise ValueError(f"Invalid special preset row: {line}")
        name, preset_type, default_param, model_name, behavior = parts
        presets.append(
            SM64SpecialPreset(
                preset_name=name,
                preset_id=ids.get(name, -1),
                preset_type=preset_type,
                default_param=int(default_param, 0),
                model_name=model_name,
                behavior=behavior,
            )
        )
    return presets


def parse_special_objects(
    path: Path, level: str, area: int, preset_ids: Dict[str, int]
) -> List[SM64SpecialObject]:
    """Parse SPECIAL_OBJECT* placements from a level's collision.inc.c.

    ``preset_ids`` is the enum SpecialPresets name->id map; it resolves preset
    aliases (e.g. special_haunted_door is an alias of special_wooden_door) so
    the placement still joins to a special_preset row by id.
    """
    special_objects = []
    for line in path.read_text().splitlines():
        line = line.strip()
        for macro in _SPECIAL_OBJECT_MACROS:
            args = extract_macro_args(line, macro)
            if args is None:
                continue
            if len(args) < 4:
                raise ValueError(f"Too few args in {macro}: {line}")
            yaw = int(args[4]) if len(args) >= 5 else 0
            special_objects.append(
                SM64SpecialObject(
                    preset_name=args[0],
                    preset_id=preset_ids.get(args[0], -1),
                    level=level,
                    area=area,
                    pos_x=int(args[1]),
                    pos_y=int(args[2]),
                    pos_z=int(args[3]),
                    yaw=yaw,
                )
            )
            break
    return special_objects
