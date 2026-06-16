from sm64_sql.behavior import parse_behaviors

BEHAVIOR_DATA_H = """\
#ifndef BEHAVIOR_DATA_H
#define BEHAVIOR_DATA_H

extern const BehaviorScript bhvStarDoor[];
extern const BehaviorScript bhvGoomba[];
extern const BehaviorScript bhvDeclaredOnly[];

#endif
"""

BEHAVIOR_DATA_C = """\
const BehaviorScript bhvStarDoor[] = {
    BEGIN(OBJ_LIST_SURFACE),
    SET_INT(oInteractType, INTERACT_DOOR),
    END_LOOP(),
};

const BehaviorScript bhvGoomba[] = {
    BEGIN(OBJ_LIST_PUSHABLE),
    CALL_NATIVE(bhv_goomba_init),
    END_LOOP(),
};
"""


def test_parse_behaviors(tmp_path):
    header = tmp_path / "behavior_data.h"
    source = tmp_path / "behavior_data.c"
    header.write_text(BEHAVIOR_DATA_H)
    source.write_text(BEHAVIOR_DATA_C)

    behaviors = parse_behaviors(header, source)
    by_name = {b.behavior_name: b.obj_list for b in behaviors}

    # Every declared behavior is listed, in header order.
    assert [b.behavior_name for b in behaviors] == [
        "bhvStarDoor",
        "bhvGoomba",
        "bhvDeclaredOnly",
    ]
    # Object list comes from the BEGIN() at the top of the script.
    assert by_name["bhvStarDoor"] == "OBJ_LIST_SURFACE"
    assert by_name["bhvGoomba"] == "OBJ_LIST_PUSHABLE"
    # A behavior declared but not defined in the .c has no object list.
    assert by_name["bhvDeclaredOnly"] == ""
