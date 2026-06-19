"""End-to-end parse against a real decomp checkout.

Set the SM64_DECOMP_PATH environment variable to the root of an
n64decomp/sm64 checkout to enable these tests; otherwise they are skipped.
"""

import json
import os
import sqlite3
from pathlib import Path

import pytest

from sm64_sql.db import write_to_db
from sm64_sql.everything import parse_repo

_decomp_env = os.environ.get("SM64_DECOMP_PATH")
_decomp = Path(_decomp_env) if _decomp_env else None

pytestmark = pytest.mark.skipif(
    _decomp is None or not (_decomp / "levels").is_dir(),
    reason="set SM64_DECOMP_PATH to a decomp checkout to run integration tests",
)


@pytest.fixture(scope="module")
def everything():
    assert _decomp is not None
    return parse_repo(_decomp)


@pytest.fixture(scope="module")
def conn(everything):
    connection = sqlite3.connect(":memory:")
    write_to_db(connection, everything)
    yield connection
    connection.close()


def test_parse_repo_finds_entities(everything):
    # Every category should be populated for a real decomp.
    assert len(everything.sm64_objects) > 0
    assert len(everything.sm64_macro_objects) > 0
    assert len(everything.sm64_models) > 0
    assert len(everything.sm64_macro_presets) > 0
    assert len(everything.sm64_levels) > 0
    assert len(everything.sm64_courses) > 0
    assert len(everything.sm64_sequences) > 0
    assert len(everything.sm64_dialogs) > 0
    assert len(everything.sm64_special_presets) > 0
    assert len(everything.sm64_special_objects) > 0
    assert len(everything.sm64_behaviors) > 0
    assert len(everything.sm64_warps) > 0
    assert len(everything.sm64_instant_warps) > 0
    assert len(everything.sm64_areas) > 0
    assert len(everything.sm64_mario_animations) > 0
    assert len(everything.sm64_sounds) > 0


def test_sounds_have_banks(everything):
    # Every sound has a SOUND_BANK_* category and a non-negative id.
    assert all(s.bank.startswith("SOUND_BANK_") for s in everything.sm64_sounds)
    assert all(s.sound_id >= 0 for s in everything.sm64_sounds)


def test_areas_join_to_dialog_and_sequence(everything):
    dialog_names = {d.dialog_name for d in everything.sm64_dialogs}
    used_dialogs = {a.dialog for a in everything.sm64_areas if a.dialog}
    # Every dialog an area shows is a real dialog.
    assert used_dialogs <= dialog_names
    # Most areas declare a background music track and a terrain type.
    assert any(a.background_music for a in everything.sm64_areas)
    assert any(a.terrain_type for a in everything.sm64_areas)


def test_warps_point_at_known_levels(everything):
    level_names = {lvl.level_name for lvl in everything.sm64_levels}
    dest_levels = {w.dest_level for w in everything.sm64_warps}
    # The connectivity graph only references defined levels.
    assert dest_levels <= level_names
    # Area 0 is a level-global warp; in-area warps use the 1-based AREA index.
    assert all(w.area >= 0 for w in everything.sm64_warps)
    assert any(w.area >= 1 for w in everything.sm64_warps)


def test_object_behaviors_are_known(everything):
    behavior_names = {b.behavior_name for b in everything.sm64_behaviors}
    used = {obj.behavior for obj in everything.sm64_objects}
    # Every behavior placed in a level should resolve to a known behavior.
    assert used <= behavior_names


def test_special_objects_reference_known_presets(everything):
    # Join by id (not name): some placements use enum aliases like
    # special_haunted_door that have no array row of their own.
    preset_ids = {p.preset_id for p in everything.sm64_special_presets}
    used = {o.preset_id for o in everything.sm64_special_objects}
    assert used <= preset_ids
    # Special objects are tagged with a real (1-based) area.
    assert all(o.area >= 1 for o in everything.sm64_special_objects)


def test_dialogs_have_text(everything):
    # Dialog text should be non-empty and ids should be unique.
    assert all(d.text for d in everything.sm64_dialogs)
    ids = [d.dialog_id for d in everything.sm64_dialogs]
    assert len(ids) == len(set(ids))


def test_levels_reference_known_courses(everything):
    course_names = {c.course_name for c in everything.sm64_courses}
    level_courses = {lvl.course_name for lvl in everything.sm64_levels}
    # Every course a level points at should be a defined course.
    assert level_courses <= course_names


def test_levels_have_folders_matching_object_levels(everything):
    folders = {lvl.folder for lvl in everything.sm64_levels if not lvl.is_stub}
    object_levels = {obj.level for obj in everything.sm64_objects}
    # The vast majority of placed-object "levels" are real level folders.
    assert "bbh" in folders
    assert object_levels & folders


def test_model_ids_are_unique_names(everything):
    names = [m.model_name for m in everything.sm64_models]
    assert len(names) == len(set(names))


def test_objects_reference_known_levels(everything):
    levels = {obj.level for obj in everything.sm64_objects}
    # A handful of well-known course folders that always exist.
    assert {"bob", "jrb"} <= levels


def test_constants_resolve_param_symbols(everything):
    constants = {c.name: c for c in everything.sm64_constants}
    assert len(constants) > 800
    # Spot-check values from each source.
    assert constants["WARP_NODE_0A"].value == 0x0A
    assert constants["WARP_NODE_0A"].source == "warp_nodes"
    assert constants["STAR_INDEX_ACT_3"].value == 2
    assert constants["STAR_INDEX_ACT_3"].source == "object_constants"

    # Every STAR_INDEX symbol used by a placed star object resolves.
    used_star_indices = {
        o.bhv_param_1
        for o in everything.sm64_objects
        if o.bhv_param_1 and o.bhv_param_1.startswith("STAR_INDEX_")
    }
    assert used_star_indices
    assert used_star_indices <= set(constants)

    # The warp-node bytes objects pass resolve too (the most common param symbol).
    used_warp_nodes = {
        o.bhv_param_2
        for o in everything.sm64_objects
        if o.bhv_param_2 and o.bhv_param_2.startswith("WARP_NODE_")
    }
    assert used_warp_nodes <= set(constants)


def test_model_loads(everything):
    loads = everything.sm64_model_loads
    assert len(loads) > 400
    # Shared common loads (Mario etc.) are recorded under the "common" level.
    assert any(m.level == "common" and m.model_name == "MODEL_MARIO" for m in loads)
    # The same model slot binds to different geo per level (the model_ids.h gap).
    geo03 = {m.geo for m in loads if m.model_name == "MODEL_LEVEL_GEOMETRY_03"}
    assert len(geo03) > 1
    # Geo loads have no layer; DL loads (present in scripts.c) keep theirs.
    assert any(m.kind == "geo" and m.layer is None for m in loads)
    dl = [m for m in loads if m.kind == "dl"]
    assert dl and all(m.layer for m in dl)
    # Loaded models resolve to the global model table.
    model_names = {m.model_name for m in everything.sm64_models}
    assert any(m.model_name in model_names for m in loads)


def test_star_and_course_names(everything):
    stars = everything.sm64_stars
    course_names = everything.sm64_course_names
    # 15 main courses x 6 acts = 90 act stars, plus the bonus-course stars.
    assert sum(1 for s in stars if s.kind == "main") == 90
    assert any(s.kind == "secret" for s in stars)
    # A famous one, in the right place.
    rolling_rocks = [s for s in stars if s.name == "WATCH FOR ROLLING ROCKS"]
    assert len(rolling_rocks) == 1
    assert rolling_rocks[0].course_name == "COURSE_HMC"
    assert rolling_rocks[0].act == 6

    # Every star/course name points at a course that exists in the course table.
    courses = {c.course_name for c in everything.sm64_courses}
    assert {s.course_name for s in stars} <= courses
    assert {c.course_name for c in course_names} <= courses
    # Main courses keep their 1-15 number; bonus courses use 0.
    numbers = {c.number for c in course_names}
    assert 1 in numbers and 15 in numbers and 0 in numbers


def test_macro_objects_include_alignment_padded_rows(everything):
    # Regression guard: the decomp aligns macro names with spaces before "(",
    # e.g. `MACRO_OBJECT   (...)`. Those rows must be parsed, not dropped. Most
    # MACRO_OBJECT placements are padded this way, so the count is in the
    # thousands, not the ~350 unpadded MACRO_OBJECT_WITH_BHV_PARAM rows.
    assert len(everything.sm64_macro_objects) > 1000
    # A concrete padded placement: BoB's act-3 star is a macro object box.
    assert any(
        mo.level == "bob" and mo.macro_name == "macro_box_star_act_3"
        for mo in everything.sm64_macro_objects
    )


def test_behavior_params_are_captured(everything):
    objects = everything.sm64_objects
    # Every object records its behavior-param expression (defaults to "0").
    assert all(o.bhv_param for o in objects)
    # Real data has a mix: many non-zero params, some numerically resolved and
    # some left symbolic (NULL value) because they reference a #define.
    assert any(o.bhv_param != "0" for o in objects)
    assert any(o.bhv_param_value is not None for o in objects)
    assert any(o.bhv_param_value is None for o in objects)
    # Warp objects expose their destination warp node in the 2nd byte (BPARAM2).
    assert any(
        o.bhv_param_2 and o.bhv_param_2.startswith("WARP_NODE_") for o in objects
    )
    # Star objects expose their act/star index in the 1st byte (BPARAM1).
    assert any(
        o.bhv_param_1 and o.bhv_param_1.startswith("STAR_INDEX_") for o in objects
    )


def test_signpost_params_join_to_dialog(everything):
    dialog_names = {d.dialog_name for d in everything.sm64_dialogs}
    signpost_dialogs = {
        mo.bhv_param
        for mo in everything.sm64_macro_objects
        if mo.macro_name == "macro_wooden_signpost"
        and mo.bhv_param.startswith("DIALOG_")
    }
    # Signposts carry a dialog id as their param, and it joins to a real dialog.
    assert signpost_dialogs
    assert signpost_dialogs <= dialog_names


def test_behavior_commands_backbone(everything):
    commands = everything.sm64_behavior_commands
    # Hundreds of scripts, thousands of commands.
    assert len(commands) > 3000
    # Every command's args_json is valid JSON (a list of strings).
    assert all(isinstance(json.loads(c.args_json), list) for c in commands)

    # Most scripts correspond to a public behavior declared in the header.
    behavior_names = {b.behavior_name for b in everything.sm64_behaviors}
    command_behaviors = {c.behavior_name for c in commands}
    assert len(command_behaviors & behavior_names) > 500
    # The only extras are internal sub-scripts defined in behavior_data.c and
    # CALL'd within it, but never exported in behavior_data.h — the command
    # backbone captures these even though the behavior table cannot.
    assert "bhvSunkenShipSetRotation" in command_behaviors - behavior_names

    # bhvGoomba's commands start with BEGIN(OBJ_LIST_PUSHABLE) and are contiguous.
    goomba = [c for c in commands if c.behavior_name == "bhvGoomba"]
    assert goomba
    assert [c.seq for c in goomba] == list(range(len(goomba)))
    assert goomba[0].command == "BEGIN"
    assert goomba[0].args == "OBJ_LIST_PUSHABLE"
    assert any(
        c.command == "CALL_NATIVE" and c.args == "bhv_goomba_update" for c in goomba
    )


def test_behavior_views_over_real_data(conn):
    cur = conn.cursor()

    # behavior_native: bhvGoomba calls its init and update functions.
    funcs = {
        row[0]
        for row in cur.execute(
            "SELECT func FROM behavior_native WHERE behavior_name = 'bhvGoomba'"
        ).fetchall()
    }
    assert {"bhv_goomba_init", "bhv_goomba_update"} <= funcs

    # behavior_spawn: Bowser spawns its flame/tail anchors; the children resolve
    # to real behaviors (a self-join on the behavior table).
    children = {
        row[0]
        for row in cur.execute(
            "SELECT s.spawned_behavior FROM behavior_spawn s "
            "JOIN behavior b ON s.spawned_behavior = b.behavior_name "
            "WHERE s.behavior_name = 'bhvBowser'"
        ).fetchall()
    }
    assert "bhvBowserBodyAnchor" in children

    # Every spawned model the view reports joins to the global model table.
    unknown_models = cur.execute(
        "SELECT COUNT(*) FROM behavior_spawn s "
        "LEFT JOIN model m ON s.spawned_model = m.model_name "
        "WHERE s.spawned_model IS NOT NULL AND m.model_name IS NULL"
    ).fetchone()[0]
    assert unknown_models == 0

    # behavior_resource: collision meshes are by far the most common resource.
    collisions = cur.execute(
        "SELECT COUNT(*) FROM behavior_resource WHERE kind = 'collision'"
    ).fetchone()[0]
    assert collisions > 50


def test_behavior_call_backbone(everything):
    calls = everything.sm64_behavior_calls
    # Hundreds of behaviors, thousands of native call sites.
    assert len(calls) > 3000
    assert len({c.behavior_name for c in calls}) > 300
    # Every row's args_json is valid JSON, and every callee is a plain
    # identifier (casts/function-pointer calls are filtered out at parse time).
    assert all(isinstance(json.loads(c.args_json), list) for c in calls)
    assert all(c.call.isidentifier() for c in calls)
    # Provenance points at real source files with 1-based line numbers.
    assert all(c.file.startswith("src/") and c.line >= 1 for c in calls)
    # Most behaviors in the call backbone are public, declared behaviors.
    behavior_names = {b.behavior_name for b in everything.sm64_behaviors}
    assert len({c.behavior_name for c in calls} & behavior_names) > 300


def test_behavior_call_relations_over_real_data(conn):
    cur = conn.cursor()

    # The headline: a spawn that exists ONLY in C, two call-levels below the
    # behavior script. bhvBobomb's act_explode does spawn_object(bhvExplosion);
    # no SPAWN_* opcode names it, so behavior_spawn cannot see it -- but the
    # reachability-attributed behavior_calls_spawn does.
    bobomb = {
        row[0]
        for row in cur.execute(
            "SELECT spawned_behavior FROM behavior_calls_spawn "
            "WHERE behavior_name = 'bhvBobomb' AND spawned_behavior IS NOT NULL"
        ).fetchall()
    }
    assert "bhvExplosion" in bobomb

    # Every resolved relation target joins to its parent table -- no danglers.
    def dangling(view, col, parent, key):
        return cur.execute(
            f"SELECT COUNT(*) FROM {view} v LEFT JOIN {parent} p "
            f"ON v.{col} = p.{key} WHERE v.{col} IS NOT NULL AND p.{key} IS NULL"
        ).fetchone()[0]

    assert (
        dangling(
            "behavior_calls_spawn", "spawned_behavior", "behavior", "behavior_name"
        )
        == 0
    )
    assert dangling("behavior_calls_spawn", "spawned_model", "model", "model_name") == 0
    assert (
        dangling(
            "behavior_calls_morph", "becomes_behavior", "behavior", "behavior_name"
        )
        == 0
    )
    assert (
        dangling("behavior_calls_seek", "target_behavior", "behavior", "behavior_name")
        == 0
    )
    assert dangling("behavior_calls_dialog", "dialog", "dialog", "dialog_name") == 0

    # Regression floors (ground truth from a source survey): a drop means
    # something stopped being captured.
    def n(view):
        return cur.execute(f"SELECT COUNT(*) FROM {view}").fetchone()[0]

    assert n("behavior_calls_spawn") > 200
    assert n("behavior_calls_sound") > 250
    assert n("behavior_calls_dialog") > 5
    assert n("behavior_calls_seek") > 20
    assert n("behavior_calls_morph") >= 5


def test_behavior_call_classification_is_complete(conn):
    # Completeness guard: a call family that any relation view claims to classify
    # must NOT also appear in the unclassified residue -- the views and the
    # audit view partition the same call space with no overlap.
    cur = conn.cursor()
    unclassified = {
        row[0]
        for row in cur.execute("SELECT call FROM behavior_call_unclassified").fetchall()
    }
    for view in (
        "behavior_calls_spawn",
        "behavior_calls_sound",
        "behavior_calls_model",
        "behavior_calls_dialog",
        "behavior_calls_morph",
        "behavior_calls_seek",
    ):
        classified = {
            row[0]
            for row in cur.execute(f"SELECT DISTINCT call FROM {view}").fetchall()
        }
        assert classified
        assert not (classified & unclassified)


def test_resolved_param_value_packs_the_bytes(everything):
    # An object with two numeric BPARAM bytes should pack them per the macros:
    # BPARAM1 -> bits 24-31, BPARAM2 -> bits 16-23.
    for o in everything.sm64_objects:
        if o.bhv_param_1 and o.bhv_param_2 and o.bhv_param_value is not None:
            assert (o.bhv_param_value >> 24) & 0xFF == int(o.bhv_param_1, 0) & 0xFF
            assert (o.bhv_param_value >> 16) & 0xFF == int(o.bhv_param_2, 0) & 0xFF
            break
    else:
        raise AssertionError("expected a fully-numeric two-byte param to exist")
