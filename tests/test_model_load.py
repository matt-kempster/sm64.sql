from sm64_sql.model_load import parse_model_loads, try_parse_model_load


def test_parse_geo_load():
    line = "LOAD_MODEL_FROM_GEO(MODEL_BOB_BUBBLY_TREE, bubbly_tree_geo),"
    load = try_parse_model_load(line, "bob")
    assert load is not None
    assert load.level == "bob"
    assert load.model_name == "MODEL_BOB_BUBBLY_TREE"
    assert load.geo == "bubbly_tree_geo"
    assert load.layer is None
    assert load.kind == "geo"


def test_parse_geo_load_with_alignment_whitespace():
    # The decomp aligns the geo column with spaces; the macro padding too.
    line = "LOAD_MODEL_FROM_GEO(MODEL_BOB_CHAIN_CHOMP_GATE,   bob_geo_000440),"
    load = try_parse_model_load(line, "bob")
    assert load is not None
    assert load.model_name == "MODEL_BOB_CHAIN_CHOMP_GATE"
    assert load.geo == "bob_geo_000440"


def test_parse_dl_load_keeps_layer():
    line = "LOAD_MODEL_FROM_DL(MODEL_X, some_dl, LAYER_OPAQUE),"
    load = try_parse_model_load(line, "wf")
    assert load is not None
    assert load.kind == "dl"
    assert load.geo == "some_dl"
    assert load.layer == "LAYER_OPAQUE"


def test_non_model_load_line_is_ignored():
    assert try_parse_model_load("RETURN(),", "bob") is None
    assert try_parse_model_load("OBJECT(MODEL_X, 0, 0, 0),", "bob") is None


def test_parse_model_loads_scans_a_file(tmp_path):
    script = tmp_path / "script.c"
    script.write_text(
        "LOAD_MODEL_FROM_GEO(MODEL_A, a_geo),\n"
        "    LOAD_MODEL_FROM_GEO(MODEL_B, b_geo),\n"
        "JUMP(0),\n"
    )
    loads = parse_model_loads(script, "ttc")
    assert [(m.model_name, m.geo) for m in loads] == [
        ("MODEL_A", "a_geo"),
        ("MODEL_B", "b_geo"),
    ]
