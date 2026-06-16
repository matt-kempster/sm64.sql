from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Tuple, Type

from sm64_sql.course import SM64Course, parse_courses
from sm64_sql.dialog import SM64Dialog, parse_dialogs
from sm64_sql.level import SM64Level, parse_levels
from sm64_sql.macro_object import SM64MacroObject, try_parse_macro_object
from sm64_sql.macro_preset import SM64MacroPreset, parse_macro_presets
from sm64_sql.model import SM64Model, parse_model_ids
from sm64_sql.object import SM64Object, try_parse_object
from sm64_sql.sequence import SM64Sequence, parse_sequences


@dataclass
class SM64Everything:
    sm64_objects: List[SM64Object]
    sm64_macro_objects: List[SM64MacroObject]
    sm64_models: List[SM64Model]
    sm64_macro_presets: List[SM64MacroPreset]
    sm64_levels: List[SM64Level]
    sm64_courses: List[SM64Course]
    sm64_sequences: List[SM64Sequence]
    sm64_dialogs: List[SM64Dialog]


# Each entry maps a SQL table to the dataclass describing its columns and the
# SM64Everything attribute holding its rows. db.write_to_db iterates this, so a
# new entity type only needs: a dataclass, a field on SM64Everything, the parse
# call in parse_repo, and one row here.
ENTITY_TABLES: List[Tuple[str, Type[Any], str]] = [
    ("object", SM64Object, "sm64_objects"),
    ("macro_object", SM64MacroObject, "sm64_macro_objects"),
    ("model", SM64Model, "sm64_models"),
    ("macro_preset", SM64MacroPreset, "sm64_macro_presets"),
    ("level", SM64Level, "sm64_levels"),
    ("course", SM64Course, "sm64_courses"),
    ("sequence", SM64Sequence, "sm64_sequences"),
    ("dialog", SM64Dialog, "sm64_dialogs"),
]


def parse_levelscript(path: Path) -> List[SM64Object]:
    script = path.read_text().splitlines()
    level_name = path.parent.name
    sm64_objects = []
    for line in script:
        line = line.strip()
        if sm64_object := try_parse_object(line, level_name):
            sm64_objects.append(sm64_object)
    return sm64_objects


def parse_macro_file(path: Path, level_name: str) -> List[SM64MacroObject]:
    script = path.read_text().splitlines()
    # TODO: figure out what to do with areas in the path
    sm64_macro_objects = []
    for line in script:
        line = line.strip()
        if sm64_macro_object := try_parse_macro_object(line, level_name):
            sm64_macro_objects.append(sm64_macro_object)
    return sm64_macro_objects


def parse_level(path: Path) -> Tuple[List[SM64Object], List[SM64MacroObject]]:
    sm64_objects = parse_levelscript(path / "script.c")
    macro_files = path.glob("**/macro.inc.c")
    sm64_macro_objects = []
    for macro_file in macro_files:
        sm64_macro_objects.extend(parse_macro_file(macro_file, path.name))
    return sm64_objects, sm64_macro_objects


def parse_repo(repo: Path) -> SM64Everything:
    sm64_objects = []
    sm64_macro_objects = []
    for level_dir in (repo / "levels").iterdir():
        if level_dir.is_dir():
            sm64_objects_level = parse_level(level_dir)
            sm64_objects.extend(sm64_objects_level[0])
            sm64_macro_objects.extend(sm64_objects_level[1])
    model_ids_file = repo / "include" / "model_ids.h"
    sm64_models = parse_model_ids(model_ids_file)
    # The preset names live in the `enum MacroPresets` in macro_presets.h. The
    # preset data array moved to macro_presets.inc.c in newer decomp revisions;
    # fall back to macro_presets.h for older trees that kept it there.
    macro_preset_names_file = repo / "include" / "macro_presets.h"
    macro_presets_file = repo / "include" / "macro_presets.inc.c"
    if not macro_presets_file.is_file():
        macro_presets_file = macro_preset_names_file
    sm64_macro_presets = parse_macro_presets(
        macro_presets_file,
        macro_preset_names_file,
    )
    sm64_levels = parse_levels(repo / "levels" / "level_defines.h")
    sm64_courses = parse_courses(repo / "levels" / "course_defines.h")
    sm64_sequences = parse_sequences(repo / "include" / "seq_ids.h")
    # Dialog text is per-language under text/<lang>/; default to US English.
    dialogs_file = repo / "text" / "us" / "dialogs.h"
    dialog_ids_file = repo / "include" / "dialog_ids.h"
    sm64_dialogs = (
        parse_dialogs(dialogs_file, dialog_ids_file) if dialogs_file.is_file() else []
    )
    return SM64Everything(
        sm64_objects=sm64_objects,
        sm64_macro_objects=sm64_macro_objects,
        sm64_models=sm64_models,
        sm64_macro_presets=sm64_macro_presets,
        sm64_levels=sm64_levels,
        sm64_courses=sm64_courses,
        sm64_sequences=sm64_sequences,
        sm64_dialogs=sm64_dialogs,
    )
