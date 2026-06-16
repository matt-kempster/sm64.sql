from sm64_sql.area import parse_areas

SCRIPT_C = """\
    AREA(/*index*/ 1, bob_geo_000488),
        TERRAIN(/*terrainData*/ bob_seg7_collision_level),
        SHOW_DIALOG(/*index*/ 0x00, DIALOG_000),
        SET_BACKGROUND_MUSIC(/*settingsPreset*/ 0x0000, /*seq*/ SEQ_LEVEL_GRASS),
        TERRAIN_TYPE(/*terrainType*/ TERRAIN_GRASS),
    END_AREA(),
    AREA(/*index*/ 2, bob_geo_other),
        TERRAIN_TYPE(/*terrainType*/ TERRAIN_WATER),
    END_AREA(),
"""


def test_parse_areas(tmp_path):
    path = tmp_path / "script.c"
    path.write_text(SCRIPT_C)
    areas = parse_areas(path, "bob")
    by_index = {a.area: a for a in areas}
    assert len(areas) == 2

    first = by_index[1]
    assert first.geo == "bob_geo_000488"
    assert first.terrain_type == "TERRAIN_GRASS"
    assert first.background_music == "SEQ_LEVEL_GRASS"
    assert first.dialog == "DIALOG_000"

    # An area without music/dialog leaves those blank but still records terrain.
    second = by_index[2]
    assert second.terrain_type == "TERRAIN_WATER"
    assert second.background_music == ""
    assert second.dialog == ""
