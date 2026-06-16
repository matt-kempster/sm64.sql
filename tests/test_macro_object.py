from sm64_sql.macro_object import try_parse_macro_object


def test_parse_macro_object_basic():
    line = (
        "MACRO_OBJECT(/*preset*/ macro_yellow_coin_2, /*yaw*/ 0, /*pos*/ 1740, 0, 900),"
    )
    obj = try_parse_macro_object(line, "bob")
    assert obj is not None
    assert obj.macro_name == "macro_yellow_coin_2"
    assert obj.level == "bob"
    assert obj.yaw == 0
    assert (obj.pos_x, obj.pos_y, obj.pos_z) == (1740, 0, 900)
    # A plain MACRO_OBJECT carries no param, so it defaults to 0.
    assert obj.bhv_param == "0"
    assert obj.bhv_param_value == 0


def test_parse_macro_object_with_bhv_param():
    line = "MACRO_OBJECT_WITH_BHV_PARAM(/*preset*/ macro_hidden_1up, /*yaw*/ 0, /*pos*/ -250, 2650, 2400, /*bhvParam*/ 2),"
    obj = try_parse_macro_object(line, "wf")
    assert obj is not None
    # The preset/yaw/pos arguments keep their positions when bhvParam is added.
    assert obj.macro_name == "macro_hidden_1up"
    assert obj.yaw == 0
    assert (obj.pos_x, obj.pos_y, obj.pos_z) == (-250, 2650, 2400)
    assert obj.bhv_param == "2"
    assert obj.bhv_param_value == 2


def test_parse_macro_object_with_symbolic_bhv_param():
    line = "MACRO_OBJECT_WITH_BHV_PARAM(/*preset*/ macro_wooden_signpost, /*yaw*/ 0, /*pos*/ 0, 0, 0, /*bhvParam*/ DIALOG_089),"
    obj = try_parse_macro_object(line, "bob")
    assert obj is not None
    assert obj.bhv_param == "DIALOG_089"
    assert obj.bhv_param_value is None


def test_macro_object_end_is_ignored():
    assert try_parse_macro_object("MACRO_OBJECT_END(),", "bob") is None


def test_macro_objects_list_macro_is_ignored():
    # MACRO_OBJECTS(objList) is a different macro and must not be matched.
    assert try_parse_macro_object("MACRO_OBJECTS(bob_macro_objs),", "bob") is None


def test_non_macro_line_returns_none():
    assert try_parse_macro_object("RETURN(),", "bob") is None
