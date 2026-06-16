from sm64_sql.mario_animation import parse_mario_animations

MARIO_ANIMATION_IDS_H = """\
enum MarioAnimID {
    /* 0x00 */ MARIO_ANIM_SLOW_LEDGE_GRAB,
    /* 0x01 */ MARIO_ANIM_FALL_OVER_BACKWARDS,
    /* 0x04 */ MARIO_ANIM_BACKFLIP,
};
"""


def test_parse_mario_animations(tmp_path):
    path = tmp_path / "mario_animation_ids.h"
    path.write_text(MARIO_ANIMATION_IDS_H)
    anims = parse_mario_animations(path)
    by_name = {a.anim_name: a.anim_id for a in anims}

    assert len(anims) == 3
    assert by_name["MARIO_ANIM_SLOW_LEDGE_GRAB"] == 0
    # Values auto-increment; the comments are just documentation.
    assert by_name["MARIO_ANIM_BACKFLIP"] == 2
