import sqlite3

from sm64_sql.area import SM64Area
from sm64_sql.behavior import SM64Behavior
from sm64_sql.course import SM64Course
from sm64_sql.db import write_to_db
from sm64_sql.dialog import SM64Dialog
from sm64_sql.everything import SM64Everything
from sm64_sql.level import SM64Level
from sm64_sql.macro_object import SM64MacroObject
from sm64_sql.macro_preset import SM64MacroPreset
from sm64_sql.mario_animation import SM64MarioAnimation
from sm64_sql.model import SM64Model
from sm64_sql.object import SM64Object
from sm64_sql.sequence import SM64Sequence
from sm64_sql.sound import SM64Sound
from sm64_sql.special import SM64SpecialObject, SM64SpecialPreset
from sm64_sql.warp import SM64InstantWarp, SM64Warp


def _everything():
    obj = SM64Object(
        model_name="MODEL_GOOMBA",
        level="bob",
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
    conn.close()
