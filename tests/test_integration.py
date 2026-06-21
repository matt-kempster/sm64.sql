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
    assert len(everything.sm64_camera_triggers) > 0
    assert len(everything.sm64_save_structs) > 0
    assert len(everything.sm64_save_fields) > 0
    assert len(everything.sm64_save_flags) > 0


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

    # Action-function-table dispatch is followed, so the large majority of the
    # ~1226 functions in src/game/behaviors/ are reached (not just the ones a
    # plain call graph sees from each CALL_NATIVE root).
    reached = {c.function for c in calls if "/behaviors/" in c.file}
    assert len(reached) > 1000


def test_behavior_call_relations_over_real_data(conn):
    cur = conn.cursor()

    # Every resolved relation target must join to its parent table (no danglers).
    def dangling(view, col, parent, key):
        return cur.execute(
            f"SELECT COUNT(*) FROM {view} v LEFT JOIN {parent} p "
            f"ON v.{col} = p.{key} WHERE v.{col} IS NOT NULL AND p.{key} IS NULL"
        ).fetchone()[0]

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

    # Action-table dispatch recovered: the exclamation box reaches the action
    # functions behind cur_obj_call_action_function(sExclamationBoxActions), one
    # of which spawns the rotating "!" mark.
    exc = {
        row[0]
        for row in cur.execute(
            "SELECT spawned_behavior FROM behavior_calls_spawn "
            "WHERE behavior_name = 'bhvExclamationBox'"
        ).fetchall()
    }
    assert "bhvRotatingExclamationMark" in exc

    # Digit-prefixed behaviors resolve (regression for the bhv[A-Z0-9] pattern):
    # Monty Mole drops a walking 1-Up.
    monty = {
        row[0]
        for row in cur.execute(
            "SELECT spawned_behavior FROM behavior_calls_spawn "
            "WHERE behavior_name = 'bhvMontyMole'"
        ).fetchall()
    }
    assert "bhv1UpWalking" in monty

    # Data-table spawns resolved interprocedurally: the exclamation box spawns
    # its whole contents table (a runtime contents->behavior lookup), including
    # the 1-Up that runs away and the caps. Every target/model still joins.
    box = {
        (row[0], row[1])
        for row in cur.execute(
            "SELECT spawned_behavior, spawned_model FROM behavior_data_spawn "
            "WHERE behavior_name = 'bhvExclamationBox'"
        ).fetchall()
    }
    assert ("bhv1UpRunningAway", "MODEL_1UP") in box
    assert ("bhvWingCap", "MODEL_MARIOS_WING_CAP") in box
    assert (
        dangling("behavior_data_spawn", "spawned_behavior", "behavior", "behavior_name")
        == 0
    )
    assert dangling("behavior_data_spawn", "spawned_model", "model", "model_name") == 0

    # behavior_all_spawns unions the three sources; every edge it reports for a
    # behavior carries a known origin and resolves.
    origins = {
        row[0]
        for row in cur.execute(
            "SELECT DISTINCT origin FROM behavior_all_spawns"
        ).fetchall()
    }
    assert origins == {"script", "c", "data"}

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

    # The relation views are resolved edges -- no NULL targets. A call that
    # passes its target as a runtime value (a signpost's dialog id read from its
    # bhv param, a spawn of a behavior held in a variable) stays in
    # behavior_call instead of showing up here as a null.
    for view, col in (
        ("behavior_calls_spawn", "spawned_behavior"),
        ("behavior_calls_sound", "sound"),
        ("behavior_calls_model", "model"),
        ("behavior_calls_dialog", "dialog"),
        ("behavior_calls_morph", "becomes_behavior"),
        ("behavior_calls_seek", "target_behavior"),
    ):
        nulls = cur.execute(
            f"SELECT COUNT(*) FROM {view} WHERE {col} IS NULL"
        ).fetchone()[0]
        assert nulls == 0, f"{view}.{col} has {nulls} NULLs"

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

    # set_mario_npc_dialog sets a Mario head-turn STATE (MARIO_DIALOG_*), not a
    # dialog id, so it is intentionally NOT a relation -- it must surface in the
    # residue rather than be silently swallowed by behavior_calls_dialog.
    assert "set_mario_npc_dialog" in unclassified


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


def test_mario_action_backbone(everything):
    actions = everything.sm64_mario_actions
    calls = everything.sm64_mario_action_calls
    # The whole action set: a couple hundred actions across all seven groups.
    assert len(actions) > 200
    assert {a.group_name for a in actions if a.group_name} == {
        "STATIONARY",
        "MOVING",
        "AIRBORNE",
        "SUBMERGED",
        "CUTSCENE",
        "AUTOMATIC",
        "OBJECT",
    }
    # Almost every action has a dispatched handler with real provenance; the few
    # that don't are the zero state and engine remap targets.
    with_handler = [a for a in actions if a.handler]
    assert len(with_handler) > 225
    assert all(a.file and a.file.startswith("src/game/mario") for a in with_handler)
    assert all(a.line and a.line >= 1 for a in with_handler)
    # ACT_UNINITIALIZED is the zero state: no group, no flags, no handler.
    uninit = next(a for a in actions if a.action_name == "ACT_UNINITIALIZED")
    assert uninit.id == "0x00000000"
    assert uninit.handler is None and uninit.group_name is None
    assert uninit.flags_json == "[]"
    # Packed flags decode from the 32-bit value.
    gp = next(a for a in actions if a.action_name == "ACT_GROUND_POUND")
    assert gp.group_name == "AIRBORNE" and "ATTACKING" in json.loads(gp.flags_json)
    # ~1000 transition-setter call sites; every callee is one of the four setters.
    assert len(calls) > 700
    assert {c.call for c in calls} <= {
        "set_mario_action",
        "drop_and_set_mario_action",
        "hurt_and_set_mario_action",
        "set_jumping_action",
    }
    assert all(c.file.startswith("src/game/mario") and c.line >= 1 for c in calls)


def test_mario_transitions_over_real_data(conn):
    cur = conn.cursor()

    def outs(action):
        return {
            row[0]
            for row in cur.execute(
                "SELECT to_action FROM mario_transition WHERE action_name = ?",
                (action,),
            ).fetchall()
        }

    # Ground-truth transitions verified against the source.
    assert "ACT_JUMP" in outs("ACT_WALKING")
    assert "ACT_GROUND_POUND" in outs("ACT_DOUBLE_JUMP")
    assert "ACT_LEDGE_GRAB" in outs("ACT_LONG_JUMP")

    # No dangling endpoints: both ends of every edge are real action nodes.
    for col in ("action_name", "to_action"):
        dangling = cur.execute(
            f"SELECT COUNT(*) FROM mario_transition t "
            f"LEFT JOIN mario_action a ON t.{col} = a.action_name "
            f"WHERE a.action_name IS NULL"
        ).fetchone()[0]
        assert dangling == 0
    # Every backbone row's source action joins the node table.
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM mario_action_call "
            "WHERE action_name NOT IN (SELECT action_name FROM mario_action)"
        ).fetchone()[0]
        == 0
    )

    # A good few hundred distinct resolved edges (regression floor).
    assert cur.execute("SELECT COUNT(*) FROM mario_transition").fetchone()[0] > 600

    # ACT_FREEFALL is a sink hub: many actions can fall into it.
    free_in = cur.execute(
        "SELECT COUNT(DISTINCT action_name) FROM mario_transition "
        "WHERE to_action = 'ACT_FREEFALL'"
    ).fetchone()[0]
    assert free_in > 30

    # ACT_BEGIN_SLIDING is an engine remap target: transitioned TO, but it has no
    # handler of its own (set_mario_action converts it to a concrete slide).
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM mario_transition WHERE to_action = 'ACT_BEGIN_SLIDING'"
        ).fetchone()[0]
        > 0
    )
    assert (
        cur.execute(
            "SELECT handler FROM mario_action WHERE action_name = 'ACT_BEGIN_SLIDING'"
        ).fetchone()[0]
        is None
    )


def test_mario_flag_gated_edges_refuted(conn):
    """Air actions reach common_air_action_step's ceiling/ledge cases in the call
    graph, but only callers that pass the stepArg flag can actually trigger them.
    The flag-gating analysis must drop the impossible edges and keep the real."""
    cur = conn.cursor()

    def into(to_action):
        return {
            row[0]
            for row in cur.execute(
                "SELECT action_name FROM mario_transition WHERE to_action = ?",
                (to_action,),
            ).fetchall()
        }

    hang = into("ACT_START_HANGING")
    ledge = into("ACT_LEDGE_GRAB")
    # Only the two air actions that pass AIR_STEP_CHECK_HANG can start hanging.
    assert "ACT_JUMP" in hang and "ACT_DOUBLE_JUMP" in hang
    # The classic false positives are gone (backflip/sideflip/etc. pass no HANG).
    for impossible in (
        "ACT_BACKFLIP",
        "ACT_SIDE_FLIP",
        "ACT_TRIPLE_JUMP",
        "ACT_LONG_JUMP",
        "ACT_FREEFALL",
        "ACT_WALL_KICK_AIR",
    ):
        assert impossible not in hang
    # Ledge grab survives where AIR_STEP_CHECK_LEDGE_GRAB is passed, and is
    # refuted for the two stepArg-0 callers (triple jump, backflip).
    assert {"ACT_LONG_JUMP", "ACT_SIDE_FLIP", "ACT_WATER_JUMP"} <= ledge
    assert "ACT_BACKFLIP" not in ledge and "ACT_TRIPLE_JUMP" not in ledge

    # The refuted edges are not silently dropped: they stay on the backbone with
    # the flag that would be required, surfaced by mario_transition_refuted.
    refuted = {
        (r[0], r[1], r[2])
        for r in cur.execute(
            "SELECT action_name, to_action, gated_by FROM mario_transition_refuted"
        ).fetchall()
    }
    assert ("ACT_BACKFLIP", "ACT_START_HANGING", "AIR_STEP_CHECK_HANG") in refuted
    assert ("ACT_BACKFLIP", "ACT_LEDGE_GRAB", "AIR_STEP_CHECK_LEDGE_GRAB") in refuted
    # Every refuted edge has a real flag and real endpoints; none leak into the
    # live transition graph.
    assert refuted and all(g.startswith("AIR_STEP_CHECK_") for _, _, g in refuted)
    live = {
        (r[0], r[1])
        for r in cur.execute(
            "SELECT action_name, to_action FROM mario_all_transitions"
        ).fetchall()
    }
    assert not any((a, t) in live for a, t, _ in refuted)


def test_mario_group_cancel_entries(conn):
    """Dispatcher-level cancels (check_common_*_cancels) run before the switch, so
    their transitions belong to the whole group. Without that, ACT_DROWNING and
    ACT_SQUISHED had no incoming edge at all."""
    cur = conn.cursor()

    def in_degree(to_action):
        return cur.execute(
            "SELECT COUNT(DISTINCT action_name) FROM mario_all_transitions "
            "WHERE to_action = ?",
            (to_action,),
        ).fetchone()[0]

    # ACT_DROWNING is reachable from many submerged actions (group cancel).
    assert in_degree("ACT_DROWNING") > 10
    # ACT_SQUISHED applies across nearly every grounded/airborne action.
    assert in_degree("ACT_SQUISHED") > 50
    # ACT_VERTICAL_WIND is entered from the airborne group cancel.
    assert in_degree("ACT_VERTICAL_WIND") > 10


def test_mario_action_residue_is_visible(conn):
    # Completeness audit: setter calls whose target is a computed/forwarded value
    # (a landing table or a parameter) stay as visible residue, never silently
    # dropped, and never overlap the resolved edges.
    cur = conn.cursor()
    residue = {
        row[0]
        for row in cur.execute(
            "SELECT target FROM mario_action_call_unclassified"
        ).fetchall()
    }
    assert residue
    # The forwarded land/end/air-action locals we know are unresolved appear here.
    assert any(t.endswith("Action") or "Action" in t for t in residue)
    real_actions = {
        row[0] for row in cur.execute("SELECT action_name FROM mario_action").fetchall()
    }
    assert not (residue & real_actions)


def test_mario_data_transitions_over_real_data(conn):
    cur = conn.cursor()

    # Forwarded land action recovered: act_jump -> ACT_JUMP_LAND through
    # common_air_action_step(m, ACT_JUMP_LAND, ...), resolved one level.
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM mario_action_data_transition "
            "WHERE action_name='ACT_JUMP' AND to_action='ACT_JUMP_LAND'"
        ).fetchone()[0]
        > 0
    )

    # Ternary branches recovered as expression literals: a double jump can
    # become a dive or a jump-kick depending on speed.
    branches = {
        row[0]
        for row in cur.execute(
            "SELECT to_action FROM mario_action_data_transition "
            "WHERE action_name='ACT_DOUBLE_JUMP' AND source='expr'"
        ).fetchall()
    }
    assert {"ACT_DIVE", "ACT_JUMP_KICK"} <= branches

    # Both endpoints are real action nodes (no danglers).
    for col in ("action_name", "to_action"):
        assert (
            cur.execute(
                f"SELECT COUNT(*) FROM mario_action_data_transition t "
                f"LEFT JOIN mario_action a ON t.{col} = a.action_name "
                f"WHERE a.action_name IS NULL"
            ).fetchone()[0]
            == 0
        )

    # Data transitions only ADD edges the literal view cannot see: a resolved edge
    # never duplicates a literal one.
    overlap = cur.execute(
        "SELECT COUNT(*) FROM mario_action_data_transition d "
        "JOIN mario_transition t "
        "ON d.action_name = t.action_name AND d.to_action = t.to_action"
    ).fetchone()[0]
    assert overlap == 0

    # mario_all_transitions is the dedup union; with no overlap it is exactly the
    # literal edges plus the resolved ones, and strictly larger than literal-only.
    lit = cur.execute("SELECT COUNT(*) FROM mario_transition").fetchone()[0]
    allt = cur.execute("SELECT COUNT(*) FROM mario_all_transitions").fetchone()[0]
    data = cur.execute("SELECT COUNT(*) FROM mario_action_data_transition").fetchone()[
        0
    ]
    assert data > 80
    assert allt == lit + data


def test_mario_transition_conditions_over_real_data(conn):
    cur = conn.cursor()

    # Most transition sites are guarded, and the trigger condition is mined.
    tot = cur.execute("SELECT COUNT(*) FROM mario_action_call").fetchone()[0]
    withc = cur.execute(
        "SELECT COUNT(*) FROM mario_action_call WHERE condition IS NOT NULL"
    ).fetchone()[0]
    assert withc > tot * 0.6

    # A known trigger, verified against the source: a jump becomes a ground-pound
    # when Z is pressed.
    gp = cur.execute(
        "SELECT condition FROM mario_action_call "
        "WHERE action_name='ACT_JUMP' AND target='ACT_GROUND_POUND' "
        "AND condition IS NOT NULL"
    ).fetchall()
    assert gp and any("INPUT_Z" in row[0] for row in gp)

    # else-branch transitions are negated, never recorded as the bare condition.
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM mario_action_call WHERE condition LIKE '!(%'"
        ).fetchone()[0]
        > 0
    )


def test_camera_triggers_over_real_data(everything):
    triggers = everything.sm64_camera_triggers
    # The decomp ships ~119 trigger rows across the wired tables.
    assert len(triggers) > 100

    # Every trigger has a numeric box and an event function name.
    assert all(t.event and t.event[0].isalpha() for t in triggers)
    assert all(
        isinstance(t.center_x, int) and isinstance(t.bounds_x, int) for t in triggers
    )

    # A known trigger, verified against the source: the BOB tower box.
    tower = [t for t in triggers if t.event == "cam_bob_tower"]
    assert tower and tower[0].camera_table == "sCamBOB"
    assert (tower[0].center_x, tower[0].center_z) == (2468, -4608)

    # Some triggers are whole-level defaults (area -1), most are area-specific.
    assert any(t.area == -1 for t in triggers)
    assert any(t.area >= 0 for t in triggers)


def test_camera_triggers_wire_to_known_levels(conn):
    cur = conn.cursor()

    # Wired tables resolve to real level folders -- no dangling level FK among
    # the rows that have one.
    dangling = cur.execute(
        "SELECT COUNT(*) FROM camera_trigger ct "
        "LEFT JOIN level l ON ct.level = l.folder "
        "WHERE ct.level IS NOT NULL AND l.folder IS NULL"
    ).fetchone()[0]
    assert dangling == 0

    # Exactly the 9 wired levels carry camera zones (bbh, castle_inside, ccm,
    # cotmc, hmc, rr, sl, ssl, thi).
    wired = cur.execute(
        "SELECT COUNT(DISTINCT level) FROM camera_trigger WHERE level IS NOT NULL"
    ).fetchone()[0]
    assert wired == 9


def test_camera_trigger_unused_table_is_surfaced(conn):
    # Completeness audit: sCamBOB is defined in camera.c but no level wires it in,
    # so it is dead code -- captured with level NULL and surfaced, not dropped.
    cur = conn.cursor()
    unused = {
        row[0]
        for row in cur.execute(
            "SELECT camera_table FROM camera_trigger_unused"
        ).fetchall()
    }
    assert "sCamBOB" in unused
    # Its rows really do have a NULL level (the FK is simply unenforced there).
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM camera_trigger "
            "WHERE camera_table = 'sCamBOB' AND level IS NULL"
        ).fetchone()[0]
        > 0
    )


def test_save_layout_over_real_data(everything):
    structs = {s.struct_name: s for s in everything.sm64_save_structs}
    # The four structs that make up the EEPROM image are all present and sized.
    assert {"SaveBlockSignature", "SaveFile", "MainMenuSaveData", "SaveBuffer"} <= set(
        structs
    )
    # Known sizes, verified against the source under the N64 ABI.
    assert structs["SaveFile"].size == 0x38  # 56 bytes
    assert structs["MainMenuSaveData"].size == 0x20  # 32 bytes

    # A few SaveFile fields land at their known offsets.
    sf = {
        f.field_name: f
        for f in everything.sm64_save_fields
        if f.struct_name == "SaveFile"
    }
    assert sf["flags"].offset == 0x08 and sf["flags"].type_name == "u32"
    assert sf["courseStars"].offset == 0x0C
    # files[NUM_SAVE_FILES][2] keeps its 4-slots x 2-backups shape.
    files = next(f for f in everything.sm64_save_fields if f.field_name == "files")
    assert files.dims == "4,2" and files.count == 8 and files.is_struct

    # The flags word: bits run 0..28 with the documented gaps (21, 22, 23 unused),
    # all single-bit, all in the "flags" group.
    flags = [f for f in everything.sm64_save_flags if f.flag_group == "flags"]
    bits = {f.bit for f in flags}
    assert {0, 1, 2, 3, 4} <= bits
    assert bits.isdisjoint({21, 22, 23})  # genuine gaps in the numbering
    assert all(bin(f.mask).count("1") == 1 for f in flags)


def test_save_buffer_is_exactly_eeprom_size(conn):
    cur = conn.cursor()
    # The completeness invariant: the root struct tiles the whole 0x200 EEPROM.
    size = cur.execute(
        "SELECT size FROM save_struct WHERE struct_name = 'SaveBuffer'"
    ).fetchone()[0]
    assert size == 0x200

    # And every struct's members account for all of its bytes -- no struct has any
    # unexplained padding (the audit view reports 0 for all of them).
    unaccounted = cur.execute(
        "SELECT COUNT(*) FROM save_struct_coverage WHERE padding_bytes != 0"
    ).fetchone()[0]
    assert unaccounted == 0


def test_save_field_struct_refs_resolve(conn):
    cur = conn.cursor()
    # Every struct-typed field points at a real save_struct row (no dangling
    # drill-in target); scalar fields (is_struct = 0) are primitives with none.
    dangling = cur.execute(
        "SELECT COUNT(*) FROM save_field f "
        "LEFT JOIN save_struct s ON f.type_name = s.struct_name "
        "WHERE f.is_struct = 1 AND s.struct_name IS NULL"
    ).fetchone()[0]
    assert dangling == 0
