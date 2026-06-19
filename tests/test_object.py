import pytest

from sm64_sql.everything import parse_levelscript
from sm64_sql.object import parse_acts, try_parse_object


def test_parse_object_defaults_area_to_zero():
    line = "OBJECT(/*model*/ MODEL_GOOMBA, /*pos*/ 1, 2, 3, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvGoomba),"
    obj = try_parse_object(line, "bob")
    assert obj is not None and obj.area == 0


def test_parse_levelscript_resolves_area_via_jump_link(tmp_path):
    # Objects defined in a local array get the area of the AREA block that
    # JUMP_LINKs that array; objects directly inside an AREA get that area; ones
    # reachable from no area stay 0.
    script = """\
static const LevelScript script_func_local_1[] = {
    OBJECT(/*model*/ MODEL_A, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvA),
};
static const LevelScript script_func_local_2[] = {
    OBJECT(/*model*/ MODEL_B, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvB),
};
static const LevelScript script_func_global_1[] = {
    OBJECT(/*model*/ MODEL_G, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvG),
};
const LevelScript level_demo_entry[] = {
    JUMP_LINK(script_func_global_1),
    AREA(/*index*/ 1, demo_geo_1),
        JUMP_LINK(script_func_local_1),
        OBJECT(/*model*/ MODEL_D, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvD),
    END_AREA(),
    AREA(/*index*/ 2, demo_geo_2),
        JUMP_LINK(script_func_local_2),
    END_AREA(),
};
"""
    level_dir = tmp_path / "demo"
    level_dir.mkdir()
    (level_dir / "script.c").write_text(script)

    objects = parse_levelscript(level_dir / "script.c")
    area_by_model = {o.model_name: o.area for o in objects}
    assert area_by_model == {
        "MODEL_A": 1,  # via JUMP_LINK(script_func_local_1) from AREA 1
        "MODEL_D": 1,  # directly inside AREA 1
        "MODEL_B": 2,  # via JUMP_LINK(script_func_local_2) from AREA 2
        "MODEL_G": 0,  # global script, not linked from any area
    }


def test_parse_object_basic_is_in_all_acts():
    line = "OBJECT(/*model*/ MODEL_GOOMBA, /*pos*/ 1, 2, 3, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvGoomba),"
    obj = try_parse_object(line, "bob")
    assert obj is not None
    assert obj.model_name == "MODEL_GOOMBA"
    assert obj.level == "bob"
    assert (obj.initial_x, obj.initial_y, obj.initial_z) == (1, 2, 3)
    assert obj.behavior == "bhvGoomba"
    assert [obj.in_act_1, obj.in_act_6] == [True, True]


def test_parse_object_basic_has_zero_param():
    line = "OBJECT(/*model*/ MODEL_GOOMBA, /*pos*/ 1, 2, 3, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvGoomba),"
    obj = try_parse_object(line, "bob")
    assert obj is not None
    assert obj.bhv_param == "0"
    assert obj.bhv_param_value == 0
    assert obj.bhv_param_1 is None and obj.bhv_param_2 is None


def test_parse_object_with_bparam_macro_does_not_crash():
    line = "OBJECT(/*model*/ MODEL_NONE, /*pos*/ 799, 1024, 4434, /*angle*/ 0, 0, 0, /*bhvParam*/ BPARAM2(184), /*bhv*/ bhvPoleGrabbing),"
    obj = try_parse_object(line, "jrb")
    assert obj is not None
    assert obj.model_name == "MODEL_NONE"
    assert obj.behavior == "bhvPoleGrabbing"
    # The 2nd byte (oBhvParams2ndByte) is captured and resolved.
    assert obj.bhv_param == "BPARAM2(184)"
    assert obj.bhv_param_2 == "184"
    assert obj.bhv_param_value == 184 << 16


def test_parse_object_symbolic_param_kept_unresolved():
    line = "OBJECT(/*model*/ MODEL_NONE, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ BPARAM1(0x01) | BPARAM2(WARP_NODE_03), /*bhv*/ bhvDoorWarp),"
    obj = try_parse_object(line, "castle_inside")
    assert obj is not None
    assert obj.bhv_param_1 == "0x01"
    assert obj.bhv_param_2 == "WARP_NODE_03"
    # A symbolic operand leaves the combined value unresolved (NULL).
    assert obj.bhv_param_value is None


def test_parse_object_with_acts_subset():
    line = "OBJECT_WITH_ACTS(/*model*/ MODEL_STAR, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvStar, /*acts*/ ACT_1 | ACT_3),"
    obj = try_parse_object(line, "bob")
    assert obj is not None
    assert [
        obj.in_act_1,
        obj.in_act_2,
        obj.in_act_3,
        obj.in_act_4,
        obj.in_act_5,
        obj.in_act_6,
    ] == [True, False, True, False, False, False]


def test_parse_object_with_acts_all():
    line = "OBJECT_WITH_ACTS(/*model*/ MODEL_STAR, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvStar, /*acts*/ ALL_ACTS),"
    obj = try_parse_object(line, "bob")
    assert obj is not None
    assert all(
        [
            obj.in_act_1,
            obj.in_act_2,
            obj.in_act_3,
            obj.in_act_4,
            obj.in_act_5,
            obj.in_act_6,
        ]
    )


def test_non_object_line_returns_none():
    assert try_parse_object("RETURN(),", "bob") is None
    assert try_parse_object("", "bob") is None


def test_object_wrong_arg_count_raises():
    with pytest.raises(ValueError):
        try_parse_object("OBJECT(a, b, c),", "bob")


def test_parse_acts():
    assert parse_acts("ALL_ACTS") == [True] * 6
    assert parse_acts("ACT_2 | ACT_5") == [False, True, False, False, True, False]
    assert parse_acts("ACT_6") == [False, False, False, False, False, True]
