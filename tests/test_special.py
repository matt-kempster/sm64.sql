from sm64_sql.special import parse_special_objects, parse_special_presets

SPECIAL_PRESETS_H = """\
enum SpecialPresets {
    special_null_start,
    special_yellow_coin,
    special_wooden_door,
    special_count
};
"""

SPECIAL_PRESETS_INC_C = """\
#include "special_presets.h"

struct SpecialPreset {
    u8 presetID;
    u8 type;
    u8 defParam;
    u8 model;
    const BehaviorScript *behavior;
};

static struct SpecialPreset sSpecialObjectPresets[] = {
    { special_null_start,  SPTYPE_YROT_NO_PARAMS,    0x00, MODEL_NONE, NULL },
    { special_yellow_coin, SPTYPE_NO_YROT_OR_PARAMS, 0x00, MODEL_YELLOW_COIN, bhvYellowCoin },
    { special_wooden_door, SPTYPE_YROT_NO_PARAMS,    0x01, MODEL_DOOR, bhvDoor }, // a door
};
"""

COLLISION_INC_C = """\
    SPECIAL_OBJECT(/*preset*/ special_yellow_coin, /*pos*/ 100, 200, 300),
    SPECIAL_OBJECT_WITH_YAW(/*preset*/ special_wooden_door, /*pos*/ -8, 1229, -1418, /*yaw*/ 192),
    SPECIAL_OBJECT_WITH_YAW_AND_PARAM(/*preset*/ special_yellow_coin, /*pos*/ 1, 2, 3, /*yaw*/ 4, /*param*/ 5),
"""


def test_parse_special_presets(tmp_path):
    names = tmp_path / "special_presets.h"
    data = tmp_path / "special_presets.inc.c"
    names.write_text(SPECIAL_PRESETS_H)
    data.write_text(SPECIAL_PRESETS_INC_C)

    presets = parse_special_presets(data, names)
    by_name = {p.preset_name: p for p in presets}
    assert len(presets) == 3

    door = by_name["special_wooden_door"]
    assert door.preset_id == 2  # enum index
    assert door.preset_type == "SPTYPE_YROT_NO_PARAMS"
    assert door.default_param == 0x01
    assert door.model_name == "MODEL_DOOR"
    assert door.behavior == "bhvDoor"

    # behavior may be NULL.
    assert by_name["special_null_start"].behavior == "NULL"


def test_parse_special_objects(tmp_path):
    path = tmp_path / "collision.inc.c"
    path.write_text(COLLISION_INC_C)

    preset_ids = {"special_yellow_coin": 1, "special_wooden_door": 2}
    objects = parse_special_objects(path, "bob", area=2, preset_ids=preset_ids)
    assert len(objects) == 3

    # Plain SPECIAL_OBJECT has no yaw; preset_id is resolved from the map.
    plain = objects[0]
    assert plain.preset_name == "special_yellow_coin"
    assert plain.preset_id == 1
    assert (plain.pos_x, plain.pos_y, plain.pos_z) == (100, 200, 300)
    assert plain.yaw == 0
    assert plain.level == "bob"
    assert plain.area == 2

    # WITH_YAW captures the yaw.
    assert objects[1].yaw == 192

    # WITH_YAW_AND_PARAM still reads yaw (the trailing param is ignored).
    assert objects[2].yaw == 4


def test_parse_special_objects_resolves_alias(tmp_path):
    path = tmp_path / "collision.inc.c"
    path.write_text("    SPECIAL_OBJECT(/*preset*/ special_haunted_door, 0, 0, 0),\n")
    # special_haunted_door aliases special_wooden_door (same id).
    preset_ids = {"special_wooden_door": 2, "special_haunted_door": 2}
    [obj] = parse_special_objects(path, "bbh", area=1, preset_ids=preset_ids)
    assert obj.preset_name == "special_haunted_door"
    assert obj.preset_id == 2  # joins to the wooden_door preset row
