import sqlite3

from sm64_sql.area import SM64Area
from sm64_sql.behavior import SM64Behavior
from sm64_sql.behavior_command import SM64BehaviorCommand
from sm64_sql.constant import SM64Constant
from sm64_sql.course import SM64Course
from sm64_sql.course_text import SM64CourseName, SM64Star
from sm64_sql.db import write_to_db
from sm64_sql.dialog import SM64Dialog
from sm64_sql.everything import SM64Everything
from sm64_sql.level import SM64Level
from sm64_sql.macro_object import SM64MacroObject
from sm64_sql.macro_preset import SM64MacroPreset
from sm64_sql.mario_animation import SM64MarioAnimation
from sm64_sql.model import SM64Model
from sm64_sql.model_load import SM64ModelLoad
from sm64_sql.object import SM64Object
from sm64_sql.sequence import SM64Sequence
from sm64_sql.sound import SM64Sound
from sm64_sql.special import SM64SpecialObject, SM64SpecialPreset
from sm64_sql.warp import SM64InstantWarp, SM64Warp


def _everything():
    obj = SM64Object(
        model_name="MODEL_GOOMBA",
        level="bob",
        area=1,
        initial_x=1,
        initial_y=2,
        initial_z=3,
        initial_rot_x=0,
        initial_rot_y=0,
        initial_rot_z=0,
        bhv_param="0",
        bhv_param_value=0,
        bhv_param_1=None,
        bhv_param_2=None,
        bhv_param_3=None,
        bhv_param_4=None,
        behavior="bhvGoomba",
        in_act_1=True,
        in_act_2=False,
        in_act_3=False,
        in_act_4=False,
        in_act_5=False,
        in_act_6=True,
    )
    return SM64Everything(
        sm64_objects=[obj],
        sm64_macro_objects=[
            SM64MacroObject(
                macro_name="macro_goomba",
                level="bob",
                area=1,
                yaw=0,
                pos_x=10,
                pos_y=20,
                pos_z=30,
                bhv_param="0",
                bhv_param_value=0,
            )
        ],
        sm64_models=[SM64Model(model_name="MODEL_GOOMBA", model_id=0x54)],
        sm64_macro_presets=[
            SM64MacroPreset(
                macro_name="macro_goomba",
                behavior="bhvGoomba",
                model_name="MODEL_GOOMBA",
                # A symbolic param resolves to NULL, exercising Optional columns.
                param="GOOMBA_SIZE_HUGE",
                param_value=None,
            )
        ],
        sm64_levels=[
            SM64Level(
                level_name="LEVEL_BOB",
                course_name="COURSE_BOB",
                folder="bob",
                internal_name="BATTLE FIELD",
                is_stub=False,
            )
        ],
        sm64_courses=[
            SM64Course(
                course_name="COURSE_BOB",
                display_name="Bob-omb Battlefield",
                dance_cutscene=0x00022240,
                is_bonus=False,
            )
        ],
        sm64_sequences=[SM64Sequence(seq_name="SEQ_LEVEL_GRASS", seq_id=0x03)],
        sm64_dialogs=[
            SM64Dialog(
                dialog_name="DIALOG_000",
                dialog_id=0,
                lines_per_box=6,
                left_offset=30,
                width=200,
                text="Hello there.",
            )
        ],
        sm64_special_presets=[
            SM64SpecialPreset(
                preset_name="special_wooden_door",
                preset_id=126,
                preset_type="SPTYPE_YROT_NO_PARAMS",
                default_param=0,
                model_name="MODEL_CASTLE_WOODEN_DOOR_UNUSED",
                behavior="bhvDoor",
            )
        ],
        sm64_special_objects=[
            SM64SpecialObject(
                preset_name="special_wooden_door",
                preset_id=126,
                level="hmc",
                area=1,
                pos_x=922,
                pos_y=-4689,
                pos_z=2330,
                yaw=192,
                bhv_param="0",
                bhv_param_value=0,
            )
        ],
        sm64_behaviors=[
            SM64Behavior(behavior_name="bhvGoomba", obj_list="OBJ_LIST_PUSHABLE")
        ],
        sm64_warps=[
            SM64Warp(
                level="bob",
                area=1,
                node_id="WARP_NODE_SUCCESS",
                dest_level="LEVEL_CASTLE",
                dest_area=1,
                dest_node="WARP_NODE_32",
                flags="WARP_NO_CHECKPOINT",
                is_painting=False,
            )
        ],
        sm64_instant_warps=[
            SM64InstantWarp(
                level="thi",
                area=1,
                warp_index=2,
                dest_area=3,
                displace_x=10240,
                displace_y=7168,
                displace_z=10240,
            )
        ],
        sm64_areas=[
            SM64Area(
                level="bob",
                area=1,
                geo="bob_geo_000488",
                terrain_type="TERRAIN_GRASS",
                background_music="SEQ_LEVEL_GRASS",
                dialog="DIALOG_000",
            )
        ],
        sm64_mario_animations=[
            SM64MarioAnimation(anim_name="MARIO_ANIM_BACKFLIP", anim_id=4)
        ],
        sm64_sounds=[
            SM64Sound(
                sound_name="SOUND_ACTION_TERRAIN_JUMP",
                sound_id=0x04008080,
                bank="SOUND_BANK_ACTION",
            )
        ],
        sm64_course_names=[
            SM64CourseName(
                course_name="COURSE_BOB", number=1, name="BOB-OMB BATTLEFIELD"
            )
        ],
        sm64_stars=[
            SM64Star(
                course_name="COURSE_BOB",
                kind="main",
                act=6,
                name="BEHIND CHAIN CHOMP'S GATE",
            )
        ],
        sm64_model_loads=[
            SM64ModelLoad(
                level="bob",
                model_name="MODEL_GOOMBA",
                geo="goomba_geo",
                layer=None,
                kind="geo",
            )
        ],
        sm64_constants=[
            SM64Constant(name="WARP_NODE_0A", value=0x0A, source="warp_nodes"),
            SM64Constant(name="STAR_INDEX_ACT_1", value=0, source="object_constants"),
        ],
        sm64_behavior_commands=[
            SM64BehaviorCommand(
                behavior_name="bhvGoomba",
                seq=0,
                command="BEGIN",
                args="OBJ_LIST_PUSHABLE",
                args_json='["OBJ_LIST_PUSHABLE"]',
            ),
            SM64BehaviorCommand(
                behavior_name="bhvGoomba",
                seq=1,
                command="CALL_NATIVE",
                args="bhv_goomba_init",
                args_json='["bhv_goomba_init"]',
            ),
            SM64BehaviorCommand(
                behavior_name="bhvGoomba",
                seq=2,
                command="SPAWN_CHILD",
                args="MODEL_GOOMBA, bhvGoomba",
                args_json='["MODEL_GOOMBA", "bhvGoomba"]',
            ),
            SM64BehaviorCommand(
                behavior_name="bhvGoomba",
                seq=3,
                command="SPAWN_CHILD_WITH_PARAM",
                args="2, MODEL_GOOMBA, bhvGoomba",
                args_json='["2", "MODEL_GOOMBA", "bhvGoomba"]',
            ),
            SM64BehaviorCommand(
                behavior_name="bhvGoomba",
                seq=4,
                command="LOAD_COLLISION_DATA",
                args="goomba_seg8_collision",
                args_json='["goomba_seg8_collision"]',
            ),
        ],
    )


def test_write_to_db_round_trip():
    conn = sqlite3.connect(":memory:")
    write_to_db(conn, _everything())

    cur = conn.cursor()
    assert cur.execute("SELECT COUNT(*) FROM object").fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM macro_object").fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM model").fetchone()[0] == 1
    assert cur.execute("SELECT COUNT(*) FROM macro_preset").fetchone()[0] == 1

    # Booleans are stored as integers and the values round-trip.
    row = cur.execute(
        "SELECT model_name, behavior, in_act_1, in_act_2 FROM object"
    ).fetchone()
    assert row == ("MODEL_GOOMBA", "bhvGoomba", 1, 0)

    # Behavior params round-trip, including Optional columns stored as NULL.
    param_row = cur.execute(
        "SELECT bhv_param, bhv_param_value, bhv_param_2 FROM object"
    ).fetchone()
    assert param_row == ("0", 0, None)
    preset_param = cur.execute("SELECT param, param_value FROM macro_preset").fetchone()
    assert preset_param == ("GOOMBA_SIZE_HUGE", None)
    # A symbolic (unresolved) value is queryable as a SQL NULL.
    assert (
        cur.execute(
            "SELECT COUNT(*) FROM macro_preset WHERE param_value IS NULL"
        ).fetchone()[0]
        == 1
    )

    # A join across the extracted tables works, which is the whole point.
    joined = cur.execute(
        "SELECT o.model_name, m.model_id FROM object o "
        "JOIN model m ON o.model_name = m.model_name"
    ).fetchone()
    assert joined == ("MODEL_GOOMBA", 0x54)

    # Objects join to the level table on the folder name.
    level_join = cur.execute(
        "SELECT l.internal_name FROM object o " "JOIN level l ON o.level = l.folder"
    ).fetchone()
    assert level_join == ("BATTLE FIELD",)

    # Objects join to the behavior table on the behavior symbol.
    behavior_join = cur.execute(
        "SELECT b.obj_list FROM object o "
        "JOIN behavior b ON o.behavior = b.behavior_name"
    ).fetchone()
    assert behavior_join == ("OBJ_LIST_PUSHABLE",)

    # An area joins to its background music (sequence) and its dialog.
    area_join = cur.execute(
        "SELECT s.seq_id, d.text FROM area a "
        "JOIN sequence s ON a.background_music = s.seq_name "
        "JOIN dialog d ON a.dialog = d.dialog_name"
    ).fetchone()
    assert area_join == (0x03, "Hello there.")

    # Stars join to the course they belong to (and to its display name).
    star_join = cur.execute(
        "SELECT c.display_name, s.act, s.name FROM star s "
        "JOIN course c ON s.course_name = c.course_name"
    ).fetchone()
    assert star_join == ("Bob-omb Battlefield", 6, "BEHIND CHAIN CHOMP'S GATE")
    # The course's in-game (file-select) name is captured too.
    ingame = cur.execute("SELECT number, name FROM course_name").fetchone()
    assert ingame == (1, "BOB-OMB BATTLEFIELD")

    # A model load joins to the global model table and stores NULL for layer.
    model_load = cur.execute(
        "SELECT ml.geo, ml.layer, m.model_id FROM model_load ml "
        "JOIN model m ON ml.model_name = m.model_name"
    ).fetchone()
    assert model_load == ("goomba_geo", None, 0x54)

    # Named constants round-trip and resolve a symbol to its integer value.
    warp_node = cur.execute(
        "SELECT value, source FROM constant WHERE name = 'WARP_NODE_0A'"
    ).fetchone()
    assert warp_node == (0x0A, "warp_nodes")

    # The behavior_command backbone keeps every command in order.
    assert cur.execute("SELECT COUNT(*) FROM behavior_command").fetchone()[0] == 5

    # The behavior_native view exposes the C function a behavior calls, and it
    # joins back to the behavior table.
    native = cur.execute(
        "SELECT n.func FROM behavior_native n "
        "JOIN behavior b ON n.behavior_name = b.behavior_name"
    ).fetchone()
    assert native == ("bhv_goomba_init",)

    # The behavior_spawn view splits the SPAWN_* opcodes into scalar columns and
    # joins to both the model and the (self-referenced) behavior table.
    spawns = cur.execute(
        "SELECT s.kind, s.spawned_model, s.spawned_behavior, s.bhv_param "
        "FROM behavior_spawn s "
        "JOIN model m ON s.spawned_model = m.model_name "
        "JOIN behavior b ON s.spawned_behavior = b.behavior_name "
        "ORDER BY s.seq"
    ).fetchall()
    assert spawns == [
        ("child", "MODEL_GOOMBA", "bhvGoomba", None),
        ("child_with_param", "MODEL_GOOMBA", "bhvGoomba", "2"),
    ]

    # The behavior_resource view exposes loaded asset symbols by kind.
    resource = cur.execute(
        "SELECT kind, symbol FROM behavior_resource WHERE behavior_name = 'bhvGoomba'"
    ).fetchone()
    assert resource == ("collision", "goomba_seg8_collision")

    # The door left open: find a command referencing a symbol in ANY arg slot.
    any_slot = cur.execute(
        "SELECT DISTINCT bc.command FROM behavior_command bc, json_each(bc.args_json) "
        "WHERE json_each.value = 'bhvGoomba' ORDER BY bc.command"
    ).fetchall()
    assert any_slot == [("SPAWN_CHILD",), ("SPAWN_CHILD_WITH_PARAM",)]
    conn.close()
