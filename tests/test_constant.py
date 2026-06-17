from sm64_sql.constant import parse_constants

LEVEL_UPDATE_H = """\
enum WarpNodes {
    WARP_NODE_00,
    WARP_NODE_01,
    WARP_NODE_0A = 0x0A,
    WARP_NODE_SUCCESS = 0xF0,
};
"""

OBJECT_CONSTANTS_H = """\
#ifndef OBJECT_CONSTANTS_H
#define OBJECT_CONSTANTS_H

#define STAR_INDEX_ACT_1 0
#define STAR_INDEX_ACT_2 1
#define GOOMBA_SIZE_HUGE 2
#define COIN_FORMATION_BP_FLAG_FLYING (1 << 4)

#endif
"""


def _parse(tmp_path):
    oc = tmp_path / "object_constants.h"
    lu = tmp_path / "level_update.h"
    oc.write_text(OBJECT_CONSTANTS_H)
    lu.write_text(LEVEL_UPDATE_H)
    return parse_constants(oc, lu)


def test_parse_constants_collects_both_sources(tmp_path):
    constants = _parse(tmp_path)
    by_name = {c.name: c for c in constants}

    assert by_name["WARP_NODE_0A"].value == 0x0A
    assert by_name["WARP_NODE_0A"].source == "warp_nodes"
    assert by_name["WARP_NODE_SUCCESS"].value == 0xF0

    assert by_name["STAR_INDEX_ACT_2"].value == 1
    assert by_name["STAR_INDEX_ACT_2"].source == "object_constants"
    assert by_name["GOOMBA_SIZE_HUGE"].value == 2
    # A shift expression resolves to its integer value.
    assert by_name["COIN_FORMATION_BP_FLAG_FLYING"].value == 0x10
    # The include guard is value-less and not collected.
    assert "OBJECT_CONSTANTS_H" not in by_name


def test_parse_constants_names_are_unique(tmp_path):
    constants = _parse(tmp_path)
    names = [c.name for c in constants]
    assert len(names) == len(set(names))


def test_parse_constants_missing_files(tmp_path):
    # Missing source files yield no constants rather than erroring.
    assert parse_constants(tmp_path / "nope.h", tmp_path / "also_nope.h") == []
