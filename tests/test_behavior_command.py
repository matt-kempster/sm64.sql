import json

from sm64_sql.behavior_command import parse_behavior_commands

BEHAVIOR_DATA_C = """\
static const BehaviorScript bhvGoomba[] = {
    BEGIN(OBJ_LIST_PUSHABLE),
    OR_INT(oFlags, (OBJ_FLAG_COMPUTE_ANGLE_TO_MARIO | OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW)),
    LOAD_ANIMATIONS(oAnimations, goomba_seg8_anims_0801DA4C),
    LOAD_COLLISION_DATA(goomba_seg8_collision),
    SET_OBJ_PHYSICS(/*Wall hitbox radius*/ 40, /*Gravity*/ -400, 0, 0, 0, 0, 0, 0),
    CALL_NATIVE(bhv_goomba_init),
    BEGIN_LOOP(),
        CALL_NATIVE(bhv_goomba_update),
    END_LOOP(),
};

const BehaviorScript bhvBowser[] = {
    BEGIN(OBJ_LIST_DESTRUCTIVE),
    SPAWN_CHILD(/*Model*/ MODEL_BOWSER_FLAME, /*Behavior*/ bhvBowserFlame),
    SPAWN_OBJ(/*Model*/ MODEL_NONE, /*Behavior*/ bhvBowserTailAnchor),
    SPAWN_CHILD_WITH_PARAM(/*Param*/ 1, /*Model*/ MODEL_NONE, /*Behavior*/ bhvFoo),
    SET_MODEL(MODEL_BOWSER),
    RETURN(),
};
"""


def _parse(tmp_path):
    path = tmp_path / "behavior_data.c"
    path.write_text(BEHAVIOR_DATA_C)
    return parse_behavior_commands(path)


def test_commands_are_grouped_and_ordered(tmp_path):
    commands = _parse(tmp_path)
    goomba = [c for c in commands if c.behavior_name == "bhvGoomba"]
    bowser = [c for c in commands if c.behavior_name == "bhvBowser"]

    # Every command in a script is captured, in source order.
    assert [c.command for c in goomba] == [
        "BEGIN",
        "OR_INT",
        "LOAD_ANIMATIONS",
        "LOAD_COLLISION_DATA",
        "SET_OBJ_PHYSICS",
        "CALL_NATIVE",
        "BEGIN_LOOP",
        "CALL_NATIVE",
        "END_LOOP",
    ]
    # seq is 0-based and contiguous, and resets for each new script.
    assert [c.seq for c in goomba] == list(range(len(goomba)))
    assert bowser[0].seq == 0


def test_args_are_split_and_json_encoded(tmp_path):
    by = {(c.behavior_name, c.seq): c for c in _parse(tmp_path)}

    # A flag expression with internal "|" stays a single argument.
    or_int = by[("bhvGoomba", 1)]
    assert json.loads(or_int.args_json) == [
        "oFlags",
        "(OBJ_FLAG_COMPUTE_ANGLE_TO_MARIO | OBJ_FLAG_SET_FACE_YAW_TO_MOVE_YAW)",
    ]

    # Inline /* ... */ comments are stripped from the arguments.
    physics = by[("bhvGoomba", 4)]
    assert json.loads(physics.args_json)[:2] == ["40", "-400"]
    assert physics.args.startswith("40, -400,")

    # A no-argument command records an empty arg list, not [""].
    begin_loop = by[("bhvGoomba", 6)]
    assert begin_loop.command == "BEGIN_LOOP"
    assert begin_loop.args == ""
    assert begin_loop.args_json == "[]"

    # CALL_NATIVE carries its single function symbol.
    assert json.loads(by[("bhvGoomba", 5)].args_json) == ["bhv_goomba_init"]


def test_spawn_argument_positions(tmp_path):
    by = {(c.behavior_name, c.seq): c for c in _parse(tmp_path)}
    # SPAWN_CHILD/SPAWN_OBJ are (model, behavior); WITH_PARAM is (param, ...).
    assert json.loads(by[("bhvBowser", 1)].args_json) == [
        "MODEL_BOWSER_FLAME",
        "bhvBowserFlame",
    ]
    assert json.loads(by[("bhvBowser", 3)].args_json) == ["1", "MODEL_NONE", "bhvFoo"]
