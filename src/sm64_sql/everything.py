import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from sm64_sql.area import SM64Area, parse_areas
from sm64_sql.behavior import SM64Behavior, parse_behaviors
from sm64_sql.behavior_call import (
    SM64BehaviorCall,
    SM64BehaviorDataSpawn,
    parse_behavior_calls,
)
from sm64_sql.behavior_command import SM64BehaviorCommand, parse_behavior_commands
from sm64_sql.camera_trigger import SM64CameraTrigger, parse_camera_triggers
from sm64_sql.constant import SM64Constant, parse_constants
from sm64_sql.course import SM64Course, parse_courses
from sm64_sql.course_text import SM64CourseName, SM64Star, parse_course_text
from sm64_sql.dialog import SM64Dialog, parse_dialogs
from sm64_sql.level import SM64Level, parse_levels
from sm64_sql.macro_object import SM64MacroObject, try_parse_macro_object
from sm64_sql.macro_preset import SM64MacroPreset, parse_macro_presets
from sm64_sql.mario_action import (
    SM64MarioAction,
    SM64MarioActionCall,
    SM64MarioActionDataTransition,
    parse_mario_actions,
)
from sm64_sql.mario_animation import SM64MarioAnimation, parse_mario_animations
from sm64_sql.model import SM64Model, parse_model_ids
from sm64_sql.model_load import SM64ModelLoad, parse_model_loads
from sm64_sql.object import SM64Object, try_parse_object
from sm64_sql.parse_utils import extract_macro_args, parse_c_enum
from sm64_sql.sequence import SM64Sequence, parse_sequences
from sm64_sql.sound import SM64Sound, parse_sounds
from sm64_sql.special import (
    SM64SpecialObject,
    SM64SpecialPreset,
    parse_special_objects,
    parse_special_presets,
)
from sm64_sql.warp import SM64InstantWarp, SM64Warp, parse_warps


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
    sm64_special_presets: List[SM64SpecialPreset]
    sm64_special_objects: List[SM64SpecialObject]
    sm64_behaviors: List[SM64Behavior]
    sm64_warps: List[SM64Warp]
    sm64_instant_warps: List[SM64InstantWarp]
    sm64_areas: List[SM64Area]
    sm64_mario_animations: List[SM64MarioAnimation]
    sm64_sounds: List[SM64Sound]
    sm64_course_names: List[SM64CourseName]
    sm64_stars: List[SM64Star]
    sm64_model_loads: List[SM64ModelLoad]
    sm64_constants: List[SM64Constant]
    sm64_behavior_commands: List[SM64BehaviorCommand]
    sm64_behavior_calls: List[SM64BehaviorCall]
    sm64_behavior_data_spawns: List[SM64BehaviorDataSpawn]
    sm64_mario_actions: List[SM64MarioAction]
    sm64_mario_action_calls: List[SM64MarioActionCall]
    sm64_mario_action_data_transitions: List[SM64MarioActionDataTransition]
    sm64_camera_triggers: List[SM64CameraTrigger]


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
    ("special_preset", SM64SpecialPreset, "sm64_special_presets"),
    ("special_object", SM64SpecialObject, "sm64_special_objects"),
    ("behavior", SM64Behavior, "sm64_behaviors"),
    ("warp", SM64Warp, "sm64_warps"),
    ("instant_warp", SM64InstantWarp, "sm64_instant_warps"),
    ("area", SM64Area, "sm64_areas"),
    ("mario_animation", SM64MarioAnimation, "sm64_mario_animations"),
    ("sound", SM64Sound, "sm64_sounds"),
    ("course_name", SM64CourseName, "sm64_course_names"),
    ("star", SM64Star, "sm64_stars"),
    ("model_load", SM64ModelLoad, "sm64_model_loads"),
    ("constant", SM64Constant, "sm64_constants"),
    ("behavior_command", SM64BehaviorCommand, "sm64_behavior_commands"),
    ("behavior_call", SM64BehaviorCall, "sm64_behavior_calls"),
    ("behavior_data_spawn", SM64BehaviorDataSpawn, "sm64_behavior_data_spawns"),
    ("mario_action", SM64MarioAction, "sm64_mario_actions"),
    ("mario_action_call", SM64MarioActionCall, "sm64_mario_action_calls"),
    (
        "mario_action_data_transition",
        SM64MarioActionDataTransition,
        "sm64_mario_action_data_transitions",
    ),
    ("camera_trigger", SM64CameraTrigger, "sm64_camera_triggers"),
]


@dataclass(frozen=True)
class ForeignKey:
    """A foreign key from this table's column to a parent table's unique column."""

    column: str
    parent_table: str
    parent_column: str


@dataclass(frozen=True)
class TableKeys:
    """Primary key, extra unique keys, and foreign keys declared on a table.

    SQLite does not *enforce* these unless ``PRAGMA foreign_keys=ON`` (and even
    then only on writes), so for this read-only database they are declarative
    metadata: they document the real join paths and let the web UI read them
    back via ``PRAGMA foreign_key_list``. They are derived from the n64decomp
    source, which has no foreign keys of its own.

    A few edges have a handful of known orphans -- pseudo-levels (``menu``,
    ``common``), the CALL'd-but-unexported ``bhvSunkenShipSetRotation``
    subroutine, the ``special_haunted_door`` preset with no preset row, and
    ``NULL``-sentinel rows. Those are genuine decomp artifacts, not schema
    errors, and are harmless while enforcement is off.
    """

    primary_key: Optional[Tuple[str, ...]] = None
    unique: Tuple[Tuple[str, ...], ...] = ()
    foreign_keys: Tuple[ForeignKey, ...] = ()


def _fk(column: str, parent_table: str, parent_column: str) -> ForeignKey:
    return ForeignKey(column, parent_table, parent_column)


# The implicit relational structure of the decomp, made explicit. Parent key
# columns are declared PRIMARY KEY / UNIQUE so they are valid FK targets (every
# one is verified unique in the data). db.write_to_db reads this when creating
# each table. Tables absent here (e.g. sound, constant) have no clean key to
# another table -- they are genuine islands.
TABLE_KEYS: Dict[str, TableKeys] = {
    # ---- hub dimension tables (parents) ----
    "level": TableKeys(
        primary_key=("level_name",),
        unique=(("folder",),),  # NULL for stubs, so still uniquely indexable
        foreign_keys=(_fk("course_name", "course", "course_name"),),
    ),
    "course": TableKeys(primary_key=("course_name",)),
    "behavior": TableKeys(primary_key=("behavior_name",)),
    "model": TableKeys(primary_key=("model_name",)),
    "sequence": TableKeys(primary_key=("seq_name",)),
    "dialog": TableKeys(primary_key=("dialog_name",)),
    "mario_animation": TableKeys(primary_key=("anim_name",)),
    "course_name": TableKeys(
        primary_key=("course_name",),
        foreign_keys=(_fk("course_name", "course", "course_name"),),
    ),
    "star": TableKeys(foreign_keys=(_fk("course_name", "course", "course_name"),)),
    # ---- presets (parents of placements, children of behavior/model) ----
    "macro_preset": TableKeys(
        primary_key=("macro_name",),
        foreign_keys=(
            _fk("behavior", "behavior", "behavior_name"),
            _fk("model_name", "model", "model_name"),
        ),
    ),
    "special_preset": TableKeys(
        primary_key=("preset_name",),
        foreign_keys=(
            _fk("behavior", "behavior", "behavior_name"),
            _fk("model_name", "model", "model_name"),
        ),
    ),
    # ---- placements (the leaves; everything flows up from here) ----
    "object": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("behavior", "behavior", "behavior_name"),
            _fk("model_name", "model", "model_name"),
        )
    ),
    "macro_object": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("macro_name", "macro_preset", "macro_name"),
        )
    ),
    "special_object": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("preset_name", "special_preset", "preset_name"),
        )
    ),
    # ---- per-level scene data ----
    "area": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("dialog", "dialog", "dialog_name"),
            _fk("background_music", "sequence", "seq_name"),
        )
    ),
    "warp": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("dest_level", "level", "level_name"),  # destination is the macro
        )
    ),
    "instant_warp": TableKeys(foreign_keys=(_fk("level", "level", "folder"),)),
    "model_load": TableKeys(
        foreign_keys=(
            _fk("level", "level", "folder"),
            _fk("model_name", "model", "model_name"),
        )
    ),
    # ---- behavior script backbone ----
    "behavior_command": TableKeys(
        foreign_keys=(_fk("behavior_name", "behavior", "behavior_name"),)
    ),
    # ---- behavior native-code backbone ----
    "behavior_call": TableKeys(
        foreign_keys=(_fk("behavior_name", "behavior", "behavior_name"),)
    ),
    "behavior_data_spawn": TableKeys(
        foreign_keys=(
            _fk("behavior_name", "behavior", "behavior_name"),
            _fk("spawned_behavior", "behavior", "behavior_name"),
            _fk("spawned_model", "model", "model_name"),
        )
    ),
    # ---- Mario's action state machine ----
    "mario_action": TableKeys(primary_key=("action_name",)),
    # The transition target lives in mario_action_call.target as a raw expression
    # (a literal ACT_*, or a computed/forwarded value), so it is not a clean FK;
    # the mario_transition view resolves the literal ones. Only the source action
    # is a declared key.
    "mario_action_call": TableKeys(
        foreign_keys=(_fk("action_name", "mario_action", "action_name"),)
    ),
    # Runtime transitions resolved to a literal action: both ends are real nodes.
    "mario_action_data_transition": TableKeys(
        foreign_keys=(
            _fk("action_name", "mario_action", "action_name"),
            _fk("to_action", "mario_action", "action_name"),
        )
    ),
    # ---- camera trigger zones (spatial, overlaid on the Map tab) ----
    # level is the folder that wires the table in, NULL for a defined-but-unused
    # table (sCamBOB); a NULL FK is simply not enforced, which is what we want.
    "camera_trigger": TableKeys(foreign_keys=(_fk("level", "level", "folder"),)),
}


# SQL views derived from the materialized tables. The behavior_command backbone
# stores each command's arguments as a JSON array (args_json); these views pull
# the high-value relations out of the opcodes that carry them, exposing plain
# scalar columns that join like every other table. The split was already done in
# the parser, so the views only select positions — no fragile SQL string-cutting.
# db.write_to_db creates these after the tables are populated.
ENTITY_VIEWS: List[Tuple[str, str]] = [
    # What each behavior spawns: SPAWN_CHILD / SPAWN_OBJ take (model, behavior);
    # SPAWN_CHILD_WITH_PARAM takes (bhvParam, model, behavior).
    (
        "behavior_spawn",
        """
        CREATE VIEW behavior_spawn AS
        SELECT behavior_name, seq,
               CASE command WHEN 'SPAWN_OBJ' THEN 'obj' ELSE 'child' END AS kind,
               json_extract(args_json, '$[0]') AS spawned_model,
               json_extract(args_json, '$[1]') AS spawned_behavior,
               NULL AS bhv_param
        FROM behavior_command
        WHERE command IN ('SPAWN_CHILD', 'SPAWN_OBJ')
        UNION ALL
        SELECT behavior_name, seq,
               'child_with_param' AS kind,
               json_extract(args_json, '$[1]') AS spawned_model,
               json_extract(args_json, '$[2]') AS spawned_behavior,
               json_extract(args_json, '$[0]') AS bhv_param
        FROM behavior_command
        WHERE command = 'SPAWN_CHILD_WITH_PARAM'
        """,
    ),
    # The native C function(s) each behavior runs (its init/loop/update code).
    (
        "behavior_native",
        """
        CREATE VIEW behavior_native AS
        SELECT behavior_name, seq, json_extract(args_json, '$[0]') AS func
        FROM behavior_command
        WHERE command = 'CALL_NATIVE'
        """,
    ),
    # Asset symbols a behavior pulls in: animation set, collision mesh, model.
    (
        "behavior_resource",
        """
        CREATE VIEW behavior_resource AS
        SELECT behavior_name, seq, 'animation' AS kind,
               json_extract(args_json, '$[1]') AS symbol
        FROM behavior_command WHERE command = 'LOAD_ANIMATIONS'
        UNION ALL
        SELECT behavior_name, seq, 'collision' AS kind,
               json_extract(args_json, '$[0]') AS symbol
        FROM behavior_command WHERE command = 'LOAD_COLLISION_DATA'
        UNION ALL
        SELECT behavior_name, seq, 'model' AS kind,
               json_extract(args_json, '$[0]') AS symbol
        FROM behavior_command WHERE command = 'SET_MODEL'
        """,
    ),
    # ----- relations mined from the native C (behavior_call backbone) -----
    # These read the same way as behavior_spawn above, but over the call sites
    # rather than the script opcodes. The target symbol is found by pattern, not
    # position, so they are robust to each helper's differing argument order: a
    # spawned behavior is the 'bhv[A-Z0-9]*' argument, a model the 'MODEL_*' one.
    # Each view lists only the sites where the target *resolves to a literal*
    # (the EXISTS guard); a call that passes its target as a runtime value -- a
    # signpost reading its dialog id from oBhvParams2ndByte, a spawn of a
    # behavior held in a variable -- stays in behavior_call but is not a clean
    # edge here. The call-name lists are the leaf relation vocabulary; anything
    # outside them shows up in behavior_call_unclassified for review.
    (
        "behavior_calls_spawn",
        """
        CREATE VIEW behavior_calls_spawn AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'bhv[A-Z0-9]*' LIMIT 1) AS spawned_behavior,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'MODEL_*' LIMIT 1) AS spawned_model
        FROM behavior_call
        WHERE call IN ('spawn_object', 'spawn_object_relative',
                       'spawn_object_relative_with_scale',
                       'spawn_object_abs_with_rot', 'spawn_object_at_origin',
                       'spawn_object_rel_with_rot', 'spawn_object_with_scale',
                       'spawn_child_obj_relative')
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'bhv[A-Z0-9]*')
        """,
    ),
    (
        "behavior_calls_sound",
        """
        CREATE VIEW behavior_calls_sound AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'SOUND_*' LIMIT 1) AS sound
        FROM behavior_call
        WHERE call IN ('cur_obj_play_sound_1', 'cur_obj_play_sound_2',
                       'cur_obj_play_sound_at_anim_range', 'play_sound',
                       'create_sound_spawner')
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'SOUND_*')
        """,
    ),
    (
        "behavior_calls_model",
        """
        CREATE VIEW behavior_calls_model AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'MODEL_*' LIMIT 1) AS model
        FROM behavior_call
        WHERE call = 'cur_obj_set_model'
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'MODEL_*')
        """,
    ),
    (
        "behavior_calls_dialog",
        """
        CREATE VIEW behavior_calls_dialog AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'DIALOG_[0-9]*' LIMIT 1) AS dialog
        FROM behavior_call
        WHERE call IN ('cur_obj_update_dialog',
                       'cur_obj_update_dialog_with_cutscene',
                       'cutscene_object_with_dialog',
                       'create_dialog_box_with_response')
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'DIALOG_[0-9]*')
        """,
    ),
    (
        "behavior_calls_morph",
        """
        CREATE VIEW behavior_calls_morph AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'bhv[A-Z0-9]*' LIMIT 1) AS becomes_behavior
        FROM behavior_call
        WHERE call IN ('cur_obj_set_behavior', 'obj_set_behavior')
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'bhv[A-Z0-9]*')
        """,
    ),
    (
        "behavior_calls_seek",
        """
        CREATE VIEW behavior_calls_seek AS
        SELECT behavior_name, function, file, line, call,
               (SELECT value FROM json_each(args_json)
                WHERE value GLOB 'bhv[A-Z0-9]*' LIMIT 1) AS target_behavior
        FROM behavior_call
        WHERE call IN ('cur_obj_nearest_object_with_behavior',
                       'obj_nearest_object_with_behavior',
                       'cur_obj_has_behavior', 'obj_has_behavior')
          AND EXISTS (SELECT 1 FROM json_each(args_json)
                      WHERE value GLOB 'bhv[A-Z0-9]*')
        """,
    ),
    # Completeness audit: every captured call site that NO relation view above
    # classifies, most-frequent first. The list is the visible residue -- scan
    # the top for any helper family we should be turning into a relation. (Math
    # and movement helpers -- sins, coss, approach_* -- legitimately live here.)
    (
        "behavior_call_unclassified",
        """
        CREATE VIEW behavior_call_unclassified AS
        SELECT call, COUNT(*) AS n
        FROM behavior_call
        WHERE call NOT IN (
            'spawn_object', 'spawn_object_relative',
            'spawn_object_relative_with_scale', 'spawn_object_abs_with_rot',
            'spawn_object_at_origin', 'spawn_object_rel_with_rot',
            'spawn_object_with_scale', 'spawn_child_obj_relative',
            'cur_obj_play_sound_1', 'cur_obj_play_sound_2',
            'cur_obj_play_sound_at_anim_range', 'play_sound',
            'create_sound_spawner', 'cur_obj_set_model',
            'cur_obj_update_dialog', 'cur_obj_update_dialog_with_cutscene',
            'cutscene_object_with_dialog', 'create_dialog_box_with_response',
            'cur_obj_set_behavior', 'obj_set_behavior',
            'cur_obj_nearest_object_with_behavior',
            'obj_nearest_object_with_behavior', 'cur_obj_has_behavior',
            'obj_has_behavior'
        )
        GROUP BY call
        ORDER BY n DESC, call
        """,
    ),
    # The complete spawn graph: the bytecode spawns (behavior_spawn), the literal
    # C spawns (behavior_calls_spawn), and the data-table / forwarded-literal
    # spawns the other two cannot resolve (behavior_data_spawn), tagged by origin.
    (
        "behavior_all_spawns",
        """
        CREATE VIEW behavior_all_spawns AS
        SELECT behavior_name, spawned_behavior, spawned_model, 'script' AS origin
        FROM behavior_spawn WHERE spawned_behavior IS NOT NULL
        UNION ALL
        SELECT behavior_name, spawned_behavior, spawned_model, 'c'
        FROM behavior_calls_spawn
        UNION ALL
        SELECT behavior_name, spawned_behavior, spawned_model, 'data'
        FROM behavior_data_spawn
        """,
    ),
    # ----- Mario's action state machine (mario_action_call backbone) -----
    # The resolved transition edges: a setter call whose target argument is a
    # literal ACT_* that names a real action. Deduplicated to one row per
    # (source, target) -- the call sites (which helper, which line) stay in
    # mario_action_call. A self-loop (an action that can re-enter itself) is kept.
    (
        "mario_transition",
        """
        CREATE VIEW mario_transition AS
        SELECT DISTINCT action_name, target AS to_action
        FROM mario_action_call
        WHERE target IN (SELECT action_name FROM mario_action)
        """,
    ),
    # Completeness audit: setter calls whose target is NOT a literal action -- a
    # forwarded parameter (endAction, landAction) or a table/struct field
    # (landingAction->endAction). These are real transitions whose destination is
    # only known at runtime; the visible residue, most-frequent first.
    (
        "mario_action_call_unclassified",
        """
        CREATE VIEW mario_action_call_unclassified AS
        SELECT target, COUNT(*) AS n
        FROM mario_action_call
        WHERE target IS NOT NULL
          AND target NOT IN (SELECT action_name FROM mario_action)
        GROUP BY target
        ORDER BY n DESC, target
        """,
    ),
    # The complete transition graph: the literal-target edges (mario_transition)
    # plus the runtime ones resolved to a literal action (forwarded land actions,
    # ternary branches) that the literal view cannot see. Deduplicated to one row
    # per (source, destination). The Actions tab reads this.
    (
        "mario_all_transitions",
        """
        CREATE VIEW mario_all_transitions AS
        SELECT action_name, to_action FROM mario_transition
        UNION
        SELECT action_name, to_action FROM mario_action_data_transition
        """,
    ),
    # ----- camera trigger zones (camera_trigger backbone) -----
    # Completeness audit: every CameraTrigger table defined in camera.c that no
    # level wires in via level_defines.h, so its rows have level = NULL. The
    # decomp ships one such dead table (sCamBOB) -- surfaced, not silently dropped.
    (
        "camera_trigger_unused",
        """
        CREATE VIEW camera_trigger_unused AS
        SELECT camera_table, COUNT(*) AS n
        FROM camera_trigger
        WHERE level IS NULL
        GROUP BY camera_table
        ORDER BY n DESC, camera_table
        """,
    ),
]


@dataclass
class _LevelData:
    """Per-level rows gathered from a single level folder."""

    objects: List[SM64Object]
    macro_objects: List[SM64MacroObject]
    special_objects: List[SM64SpecialObject]
    warps: List[SM64Warp]
    instant_warps: List[SM64InstantWarp]
    areas: List[SM64Area]
    model_loads: List[SM64ModelLoad]


def area_from_path(path: Path) -> int:
    """Return the area number from a path like levels/bob/areas/1/file.c (else 0)."""
    parts = path.parts
    if "areas" in parts:
        index = parts.index("areas")
        if index + 1 < len(parts):
            try:
                return int(parts[index + 1])
            except ValueError:
                pass
    return 0


def parse_levelscript(path: Path) -> List[SM64Object]:
    """Parse OBJECT placements from a level script.c, tagging each with its AREA.

    Objects live in ``static const LevelScript script_func_local_N[]`` arrays
    that an AREA block pulls in with ``JUMP_LINK``, so an object's area is the
    area whose block JUMP_LINKs the array the object is defined in (or, when an
    OBJECT sits directly inside an AREA block, that area). Objects reachable from
    no area -- e.g. shared global scripts -- keep area 0.
    """
    level_name = path.parent.name
    tagged: List[Tuple[SM64Object, Optional[str]]] = []  # (object, container key)
    area_of_array: Dict[str, int] = {}
    container: Optional[str] = None  # current array name, or "@<n>" inside an AREA
    current_area: Optional[int] = None

    for raw in path.read_text().splitlines():
        line = raw.strip()

        array_match = re.match(r"static const LevelScript (\w+)\[\]", line)
        if array_match:
            container = array_match.group(1)
            current_area = None
            continue

        area_args = extract_macro_args(line, "AREA")
        if area_args is not None:
            try:
                current_area = int(area_args[0])
            except ValueError:
                current_area = 0
            container = f"@{current_area}"
            continue
        if line.startswith("END_AREA"):
            current_area = None
            container = None
            continue

        if current_area is not None:
            jump = extract_macro_args(line, "JUMP_LINK")
            if jump:
                area_of_array[jump[0]] = current_area
                continue

        if sm64_object := try_parse_object(line, level_name):
            tagged.append((sm64_object, container))

    objects: List[SM64Object] = []
    for sm64_object, container in tagged:
        if container is not None and container.startswith("@"):
            sm64_object.area = int(container[1:])
        elif container is not None:
            sm64_object.area = area_of_array.get(container, 0)
        else:
            sm64_object.area = 0
        objects.append(sm64_object)
    return objects


def parse_macro_file(path: Path, level_name: str) -> List[SM64MacroObject]:
    # Macro arrays live at levels/<lvl>/areas/<n>/macro.inc.c, so the area is the
    # number in the path.
    area = area_from_path(path)
    sm64_macro_objects = []
    for line in path.read_text().splitlines():
        if sm64_macro_object := try_parse_macro_object(line.strip(), level_name, area):
            sm64_macro_objects.append(sm64_macro_object)
    return sm64_macro_objects


def parse_level(path: Path, special_preset_ids: Dict[str, int]) -> _LevelData:
    script = path / "script.c"
    objects = parse_levelscript(script) if script.is_file() else []
    warps, instant_warps = (
        parse_warps(script, path.name) if script.is_file() else ([], [])
    )
    areas = parse_areas(script, path.name) if script.is_file() else []
    model_loads = parse_model_loads(script, path.name) if script.is_file() else []

    macro_objects = []
    for macro_file in path.glob("**/macro.inc.c"):
        macro_objects.extend(parse_macro_file(macro_file, path.name))

    special_objects = []
    for collision_file in path.glob("**/collision.inc.c"):
        special_objects.extend(
            parse_special_objects(
                collision_file,
                path.name,
                area_from_path(collision_file),
                special_preset_ids,
            )
        )
    return _LevelData(
        objects=objects,
        macro_objects=macro_objects,
        special_objects=special_objects,
        warps=warps,
        instant_warps=instant_warps,
        areas=areas,
        model_loads=model_loads,
    )


def parse_repo(repo: Path) -> SM64Everything:
    special_preset_names_file = repo / "include" / "special_presets.h"
    special_preset_ids = dict(
        parse_c_enum(special_preset_names_file.read_text(), "SpecialPresets")
    )

    sm64_objects = []
    sm64_macro_objects = []
    sm64_special_objects = []
    sm64_warps = []
    sm64_instant_warps = []
    sm64_areas = []
    sm64_model_loads = []
    for level_dir in (repo / "levels").iterdir():
        if level_dir.is_dir():
            level_data = parse_level(level_dir, special_preset_ids)
            sm64_objects.extend(level_data.objects)
            sm64_macro_objects.extend(level_data.macro_objects)
            sm64_special_objects.extend(level_data.special_objects)
            sm64_warps.extend(level_data.warps)
            sm64_instant_warps.extend(level_data.instant_warps)
            sm64_areas.extend(level_data.areas)
            sm64_model_loads.extend(level_data.model_loads)
    # The shared levels/scripts.c loads the common models (Mario, effects, ...)
    # for every level; record those under the "common" pseudo-level.
    shared_script = repo / "levels" / "scripts.c"
    if shared_script.is_file():
        sm64_model_loads.extend(parse_model_loads(shared_script, "common"))
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
    # Special preset data moved to special_presets.inc.c; names stay in the
    # enum SpecialPresets in special_presets.h (read above for id resolution).
    special_presets_file = repo / "include" / "special_presets.inc.c"
    if not special_presets_file.is_file():
        special_presets_file = special_preset_names_file
    sm64_special_presets = parse_special_presets(
        special_presets_file, special_preset_names_file
    )
    behavior_data_c = repo / "data" / "behavior_data.c"
    sm64_behaviors = parse_behaviors(
        repo / "include" / "behavior_data.h",
        behavior_data_c,
    )
    # The ordered command stream of every behavior script (the backbone the
    # behavior_spawn / behavior_native / behavior_resource views read from).
    sm64_behavior_commands = (
        parse_behavior_commands(behavior_data_c) if behavior_data_c.is_file() else []
    )
    # The C code each behavior runs, mined from src/game/behaviors/. The roots
    # are the CALL_NATIVE functions in the command stream above; reachability
    # from them attributes every call site to its behavior(s).
    root_to_behaviors: Dict[str, List[str]] = {}
    for command in sm64_behavior_commands:
        if command.command == "CALL_NATIVE" and command.args:
            root_to_behaviors.setdefault(command.args, [])
            if command.behavior_name not in root_to_behaviors[command.args]:
                root_to_behaviors[command.args].append(command.behavior_name)
    parsed_behavior_code = parse_behavior_calls(repo, root_to_behaviors)
    sm64_behavior_calls = parsed_behavior_code.calls
    sm64_behavior_data_spawns = parsed_behavior_code.data_spawns
    # Mario's action state machine: the ACT_* nodes and the transitions mined
    # from each action handler's reachable C code (src/game/mario*.c).
    parsed_mario_actions = parse_mario_actions(repo)
    sm64_mario_actions = parsed_mario_actions.actions
    sm64_mario_action_calls = parsed_mario_actions.calls
    sm64_mario_action_data_transitions = parsed_mario_actions.data_transitions
    # Camera trigger zones: world-space boxes that switch the camera's behaviour
    # while Mario is inside them. Overlaid on the Map tab. The defined-but-unused
    # sCamBOB table is captured too (its rows resolve to level = NULL).
    sm64_camera_triggers = parse_camera_triggers(repo)
    sm64_mario_animations = parse_mario_animations(
        repo / "include" / "mario_animation_ids.h"
    )
    sm64_sounds = parse_sounds(repo / "include" / "sounds.h")
    # Course and star names are per-language under text/<lang>/; default to US.
    courses_text_file = repo / "text" / "us" / "courses.h"
    if courses_text_file.is_file():
        sm64_course_names, sm64_stars = parse_course_text(courses_text_file)
    else:
        sm64_course_names, sm64_stars = [], []
    # Named integer constants used by behavior params (WARP_NODE_*, STAR_INDEX_*).
    sm64_constants = parse_constants(
        repo / "include" / "object_constants.h",
        repo / "src" / "game" / "level_update.h",
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
        sm64_special_presets=sm64_special_presets,
        sm64_special_objects=sm64_special_objects,
        sm64_behaviors=sm64_behaviors,
        sm64_warps=sm64_warps,
        sm64_instant_warps=sm64_instant_warps,
        sm64_areas=sm64_areas,
        sm64_mario_animations=sm64_mario_animations,
        sm64_sounds=sm64_sounds,
        sm64_course_names=sm64_course_names,
        sm64_stars=sm64_stars,
        sm64_model_loads=sm64_model_loads,
        sm64_constants=sm64_constants,
        sm64_behavior_commands=sm64_behavior_commands,
        sm64_behavior_calls=sm64_behavior_calls,
        sm64_behavior_data_spawns=sm64_behavior_data_spawns,
        sm64_mario_actions=sm64_mario_actions,
        sm64_mario_action_calls=sm64_mario_action_calls,
        sm64_mario_action_data_transitions=sm64_mario_action_data_transitions,
        sm64_camera_triggers=sm64_camera_triggers,
    )
