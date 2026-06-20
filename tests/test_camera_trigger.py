"""Unit tests for the camera-trigger parser.

These build a tiny fake decomp tree on disk -- a levels/level_defines.h wiring
one camera table to a folder and an src/game/camera.c with two trigger tables
(one wired, one not) plus the master pointer array -- so the row decoding, the
table->folder resolution, the doc capture, and the unused-table handling can all
be exercised without a full checkout.
"""

from pathlib import Path

from sm64_sql.camera_trigger import parse_camera_triggers

# bob -> sCamBOB (wired); sl -> _ (no table). sCamUnused below is referenced by
# nobody, so it is dead code and must resolve to level = None.
_LEVEL_DEFINES = """\
DEFINE_LEVEL("BATTLE FIELD", LEVEL_BOB, COURSE_BOB, bob, generic, 15000, 0x08, 0x08, 0x08, _, sCamBOB)
DEFINE_LEVEL("YUKIYAMA2",    LEVEL_SL,  COURSE_SL,  sl,  snow,    14000, 0x10, 0x28, 0x28, _, _)
"""

_CAMERA_C = """\
/**
 * The BOB triggers control the tower camera.
 * Second comment line.
 */
struct CameraTrigger sCamBOB[] = {
    {  1, cam_bob_tower, 2468, 2720, -4608, 3263, 1696, 3072, 0x2000 },
    { -1, cam_bob_default_free_roam, 0, 0, 0, 0, 0, 0, 0 },
    NULL_TRIGGER
};

// A leftover table nobody wires in.
struct CameraTrigger sCamUnused[] = {
    { 1, cam_unused, -100, 0, 200, 50, 60, 70, -0x1D27 },
    NULL_TRIGGER
};

struct CameraTrigger *sCameraTriggers[LEVEL_COUNT + 1] = {
    NULL,
    sCamBOB,
    sCamUnused,
};
"""


def _fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "levels").mkdir()
    (tmp_path / "levels" / "level_defines.h").write_text(_LEVEL_DEFINES)
    game = tmp_path / "src" / "game"
    game.mkdir(parents=True)
    (game / "camera.c").write_text(_CAMERA_C)
    return tmp_path


def test_wired_table_rows_decoded(tmp_path: Path):
    triggers = parse_camera_triggers(_fake_repo(tmp_path))
    bob = [t for t in triggers if t.camera_table == "sCamBOB"]
    # NULL_TRIGGER is skipped, so exactly the two real rows remain, in order.
    assert [t.seq for t in bob] == [0, 1]
    assert all(t.level == "bob" for t in bob)

    tower = bob[0]
    assert tower.area == 1
    assert tower.event == "cam_bob_tower"
    assert (tower.center_x, tower.center_y, tower.center_z) == (2468, 2720, -4608)
    assert (tower.bounds_x, tower.bounds_y, tower.bounds_z) == (3263, 1696, 3072)
    assert tower.bounds_yaw == 0x2000  # hex angle decoded
    assert tower.file == "src/game/camera.c"
    assert tower.line == 6  # 1-based line of the first row


def test_default_area_is_negative_one(tmp_path: Path):
    triggers = parse_camera_triggers(_fake_repo(tmp_path))
    default = next(t for t in triggers if t.event == "cam_bob_default_free_roam")
    assert default.area == -1
    assert (default.bounds_x, default.bounds_y, default.bounds_z) == (0, 0, 0)


def test_doc_comment_captured(tmp_path: Path):
    triggers = parse_camera_triggers(_fake_repo(tmp_path))
    bob = next(t for t in triggers if t.camera_table == "sCamBOB")
    assert bob.doc is not None
    assert "BOB triggers control the tower camera" in bob.doc
    assert "Second comment line." in bob.doc  # multi-line block joined
    # The single-line // comment above sCamUnused is captured too.
    unused = next(t for t in triggers if t.camera_table == "sCamUnused")
    assert unused.doc == "A leftover table nobody wires in."


def test_unused_table_has_null_level(tmp_path: Path):
    triggers = parse_camera_triggers(_fake_repo(tmp_path))
    unused = [t for t in triggers if t.camera_table == "sCamUnused"]
    assert len(unused) == 1
    assert unused[0].level is None
    assert unused[0].bounds_yaw == -0x1D27  # negative hex decoded


def test_master_pointer_array_not_captured(tmp_path: Path):
    triggers = parse_camera_triggers(_fake_repo(tmp_path))
    # The `struct CameraTrigger *sCameraTriggers[]` dispatch array is not a data
    # table and must not appear among the captured tables.
    assert all(t.camera_table != "sCameraTriggers" for t in triggers)
    assert {t.camera_table for t in triggers} == {"sCamBOB", "sCamUnused"}


def test_missing_file_returns_empty(tmp_path: Path):
    # No camera.c at all -> empty, not an error.
    (tmp_path / "levels").mkdir()
    (tmp_path / "levels" / "level_defines.h").write_text(_LEVEL_DEFINES)
    assert parse_camera_triggers(tmp_path) == []
