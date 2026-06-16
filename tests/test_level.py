from sm64_sql.level import parse_levels

LEVEL_DEFINES_H = """\
#ifdef VERSION_JP
#define VAL_DIFF 25000
#else
#define VAL_DIFF 60000
#endif

STUB_LEVEL(  "",             LEVEL_UNKNOWN_1, COURSE_NONE,              20000, 0x00, 0x00, 0x00, _, _)
DEFINE_LEVEL("TERESA OBAKE", LEVEL_BBH,       COURSE_BBH,  bbh, spooky, 28000, 0x28, 0x28, 0x28, _, sCamBBH)
DEFINE_LEVEL("KUPPA1",       LEVEL_BOWSER_1,  COURSE_BITDW, bowser_1, generic, VAL_DIFF, 0x40, 0x40, 0x40, _, _)
"""


def test_parse_levels(tmp_path):
    path = tmp_path / "level_defines.h"
    path.write_text(LEVEL_DEFINES_H)
    levels = parse_levels(path)
    by_name = {lvl.level_name: lvl for lvl in levels}

    assert len(levels) == 3

    bbh = by_name["LEVEL_BBH"]
    assert bbh.course_name == "COURSE_BBH"
    assert bbh.folder == "bbh"
    assert bbh.internal_name == "TERESA OBAKE"
    assert bbh.is_stub is False

    # STUB_LEVEL has no folder and an empty internal name.
    stub = by_name["LEVEL_UNKNOWN_1"]
    assert stub.is_stub is True
    assert stub.folder == ""
    assert stub.internal_name == ""

    # A level whose enum course differs from its level enum still maps right.
    assert by_name["LEVEL_BOWSER_1"].course_name == "COURSE_BITDW"
