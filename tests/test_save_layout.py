"""Unit tests for the save-file layout engine.

These build a tiny fake decomp tree -- an include/types.h with the Vec3s alias,
a levels/course_defines.h to resolve the course counts, and an
src/game/save_file.h with the real save structs (including the EU-only field
behind ``#ifdef VERSION_EU`` and the ``sizeof``-based EEPROM filler) -- so the
ABI sizing, the constant/sizeof resolution, the version-branch selection, and
the bit decode can all be exercised without a full checkout.
"""

from pathlib import Path

from sm64_sql.save_layout import parse_save_layout

_TYPES_H = "typedef short s16;\ntypedef s16 Vec3s[3];\n"

# Two main courses (COURSE_NONE + COURSE_BOB) and one bonus, so
# COURSE_STAGES_COUNT == 1 and COURSE_COUNT == 2.
_COURSE_DEFINES = """\
DEFINE_COURSE(COURSE_NONE, 0x44444440) // (0) Hub
DEFINE_COURSE(COURSE_BOB,  0x00022240) // (1) Bob-omb Battlefield
DEFINE_COURSES_END()
DEFINE_BONUS_COURSE(COURSE_BITDW, 0x34444440) // (2) Bowser in the Dark World
"""

# A faithfully-shaped save_file.h: the EU field/SUBTRAHEND live behind
# #ifdef VERSION_EU, the filler is sized off sizeof(struct SaveFile), and the
# flags word has a deliberate gap (no bit 2) plus a function-like macro to skip.
_SAVE_FILE_H = """\
#ifndef SAVE_FILE_H
#define SAVE_FILE_H

#define EEPROM_SIZE 0x200
#define NUM_SAVE_FILES 4

struct SaveBlockSignature {
    u16 magic;
    u16 chksum;
};

struct SaveFile {
    // Location of lost cap.
    u8 capLevel;
    u8 capArea;
    Vec3s capPos;
    u32 flags;
    // Star flags for each course.
    u8 courseStars[COURSE_COUNT];
    u8 courseCoinScores[COURSE_STAGES_COUNT];
    struct SaveBlockSignature signature;
};

struct MainMenuSaveData {
    u32 coinScoreAges[NUM_SAVE_FILES];
    u16 soundMode;
#ifdef VERSION_EU
    u16 language;
#define SUBTRAHEND 8
#else
#define SUBTRAHEND 6
#endif
    u8 filler[EEPROM_SIZE / 2 - SUBTRAHEND - NUM_SAVE_FILES * (4 + sizeof(struct SaveFile))];
    struct SaveBlockSignature signature;
};

struct SaveBuffer {
    struct SaveFile files[NUM_SAVE_FILES][2];
    struct MainMenuSaveData menuData[2];
};

struct WarpCheckpoint {
    u8 actNum;
};

#define SAVE_FLAG_FILE_EXISTS   /* 0x01 */ (1 << 0)
#define SAVE_FLAG_HAVE_WING_CAP /* 0x02 */ (1 << 1)
#define SAVE_FLAG_HAVE_KEY_1    /* 0x10 */ (1 << 4)
#define SAVE_FLAG_TO_STAR_FLAG(cmd) (((cmd) >> 24) & 0x7F)

#endif
"""


def _fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "types.h").write_text(_TYPES_H)
    (tmp_path / "levels").mkdir()
    (tmp_path / "levels" / "course_defines.h").write_text(_COURSE_DEFINES)
    game = tmp_path / "src" / "game"
    game.mkdir(parents=True)
    (game / "save_file.h").write_text(_SAVE_FILE_H)
    return tmp_path


def test_struct_sizes_and_eeprom_invariant(tmp_path: Path):
    parsed = parse_save_layout(_fake_repo(tmp_path))
    sizes = {s.struct_name: s.size for s in parsed.structs}
    # SaveFile: 1+1 + Vec3s(6) + u32(4) + courseStars(COURSE_COUNT=2)
    #           + courseCoinScores(COURSE_STAGES_COUNT=1) + signature(4)
    #         = 1+1+6+4+2+1+4 = 19, padded to align 4 -> 20.
    assert sizes["SaveFile"] == 20
    assert sizes["SaveBlockSignature"] == 4
    # The whole buffer is exactly EEPROM_SIZE -- the completeness invariant.
    assert sizes["SaveBuffer"] == 0x200


def test_alignment_padding_is_applied(tmp_path: Path):
    parsed = parse_save_layout(_fake_repo(tmp_path))
    fields = {f.field_name: f for f in parsed.fields if f.struct_name == "SaveFile"}
    # capPos (Vec3s, align 2) starts right after the two u8s at offset 2.
    assert fields["capPos"].offset == 2
    assert (fields["capPos"].type_name, fields["capPos"].size) == ("Vec3s", 6)
    # flags (u32, align 4) lands at offset 8, after the 8-byte cap block.
    assert fields["flags"].offset == 8


def test_filler_uses_sizeof_and_us_branch(tmp_path: Path):
    parsed = parse_save_layout(_fake_repo(tmp_path))
    fields = {
        f.field_name: f for f in parsed.fields if f.struct_name == "MainMenuSaveData"
    }
    # The EU `language` field is behind #ifdef VERSION_EU -> excluded from the
    # default layout entirely.
    assert "language" not in fields
    # filler = EEPROM_SIZE/2 - SUBTRAHEND(6, the #else) - NUM_SAVE_FILES*(4 + 20)
    #        = 256 - 6 - 4*24 = 154.
    assert fields["filler"].size == 256 - 6 - 4 * (4 + 20)


def test_array_dims_and_struct_drill_in(tmp_path: Path):
    parsed = parse_save_layout(_fake_repo(tmp_path))
    buf = {f.field_name: f for f in parsed.fields if f.struct_name == "SaveBuffer"}
    # files[NUM_SAVE_FILES][2] keeps its shape (4 slots x 2 backups) and counts 8.
    assert buf["files"].dims == "4,2"
    assert buf["files"].count == 8
    assert buf["files"].is_struct and buf["files"].type_name == "SaveFile"


def test_runtime_only_struct_excluded(tmp_path: Path):
    # WarpCheckpoint is in the header but not reachable from SaveBuffer, so it is
    # not part of the saved layout and must not be emitted.
    parsed = parse_save_layout(_fake_repo(tmp_path))
    assert "WarpCheckpoint" not in {s.struct_name for s in parsed.structs}


def test_flag_bits_decoded_with_gaps(tmp_path: Path):
    parsed = parse_save_layout(_fake_repo(tmp_path))
    bits = {f.flag_name: f.bit for f in parsed.flags}
    assert bits == {
        "SAVE_FLAG_FILE_EXISTS": 0,
        "SAVE_FLAG_HAVE_WING_CAP": 1,
        "SAVE_FLAG_HAVE_KEY_1": 4,
    }
    # The function-like conversion macro is not a flag and is skipped.
    assert "SAVE_FLAG_TO_STAR_FLAG" not in bits
    # Bit 4 carries its 1 << 4 mask; bits 2 and 3 are genuine gaps.
    key1 = next(f for f in parsed.flags if f.flag_name == "SAVE_FLAG_HAVE_KEY_1")
    assert key1.mask == 0x10
    assert key1.flag_group == "flags"


def test_missing_file_returns_empty(tmp_path: Path):
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "types.h").write_text(_TYPES_H)
    parsed = parse_save_layout(tmp_path)
    assert parsed.structs == [] and parsed.fields == [] and parsed.flags == []
