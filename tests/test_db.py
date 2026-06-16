import sqlite3

from sm64_sql.course import SM64Course
from sm64_sql.db import write_to_db
from sm64_sql.dialog import SM64Dialog
from sm64_sql.everything import SM64Everything
from sm64_sql.level import SM64Level
from sm64_sql.macro_object import SM64MacroObject
from sm64_sql.macro_preset import SM64MacroPreset
from sm64_sql.model import SM64Model
from sm64_sql.object import SM64Object
from sm64_sql.sequence import SM64Sequence


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
            )
        ],
        sm64_models=[SM64Model(model_name="MODEL_GOOMBA", model_id=0x54)],
        sm64_macro_presets=[
            SM64MacroPreset(
                macro_name="macro_goomba",
                behavior="bhvGoomba",
                model_name="MODEL_GOOMBA",
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
    conn.close()
