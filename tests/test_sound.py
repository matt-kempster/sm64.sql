from sm64_sql.sound import parse_sounds

SOUNDS_H = """\
#define SOUND_BANK_ACTION 0

#define SOUND_ARG_LOAD(bank, soundID, priority, flags) (\\
    ((bank) << 28) | ((soundID) << 16))

#define SOUND_ACTION_TERRAIN_JUMP   /* 0x04008080 */ SOUND_ARG_LOAD(SOUND_BANK_ACTION, 0x00, 0x80, SOUND_DISCRETE)
#define SOUND_ACTION_TERRAIN_LANDING /* 0x04088080 */ SOUND_ARG_LOAD(SOUND_BANK_ACTION, 0x08, 0x80, SOUND_DISCRETE)
"""


def test_parse_sounds(tmp_path):
    path = tmp_path / "sounds.h"
    path.write_text(SOUNDS_H)
    sounds = parse_sounds(path)
    by_name = {s.sound_name: s for s in sounds}

    # The helper macro and the bank define are not sound effects.
    assert "SOUND_ARG_LOAD" not in by_name
    assert "SOUND_BANK_ACTION" not in by_name
    assert len(sounds) == 2

    jump = by_name["SOUND_ACTION_TERRAIN_JUMP"]
    assert jump.sound_id == 0x04008080  # read straight from the comment
    assert jump.bank == "SOUND_BANK_ACTION"
