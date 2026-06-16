import pytest

from sm64_sql.object import parse_acts, try_parse_object


def test_parse_object_basic_is_in_all_acts():
    line = "OBJECT(/*model*/ MODEL_GOOMBA, /*pos*/ 1, 2, 3, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvGoomba),"
    obj = try_parse_object(line, "bob")
    assert obj is not None
    assert obj.model_name == "MODEL_GOOMBA"
    assert obj.level == "bob"
    assert (obj.initial_x, obj.initial_y, obj.initial_z) == (1, 2, 3)
    assert obj.behavior == "bhvGoomba"
    assert [obj.in_act_1, obj.in_act_6] == [True, True]


def test_parse_object_with_bparam_macro_does_not_crash():
    line = "OBJECT(/*model*/ MODEL_NONE, /*pos*/ 799, 1024, 4434, /*angle*/ 0, 0, 0, /*bhvParam*/ BPARAM2(184), /*bhv*/ bhvPoleGrabbing),"
    obj = try_parse_object(line, "jrb")
    assert obj is not None
    assert obj.model_name == "MODEL_NONE"
    assert obj.behavior == "bhvPoleGrabbing"


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
