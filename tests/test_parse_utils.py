from sm64_sql.parse_utils import (
    extract_macro_args,
    parse_c_enum,
    split_top_level,
    strip_block_comments,
    strip_comments_and_whitespace,
)


def test_split_top_level_plain():
    assert split_top_level("a, b, c") == ["a", " b", " c"]


def test_split_top_level_ignores_nested_commas():
    # A comma inside parentheses is part of an argument, not a separator.
    assert split_top_level("a, f(b, c), d") == ["a", " f(b, c)", " d"]


def test_split_top_level_handles_brackets_and_braces():
    assert split_top_level("{a, b}, [c, d]") == ["{a, b}", " [c, d]"]


def test_split_top_level_no_separator():
    assert split_top_level("BPARAM1(0) | BPARAM2(1)") == ["BPARAM1(0) | BPARAM2(1)"]


def test_strip_block_comments_keeps_surrounding_text():
    assert strip_block_comments("a /*x*/ b /*y*/ c") == "a  b  c"


def test_strip_comments_and_whitespace_trims():
    assert strip_comments_and_whitespace("  /*pos*/  900  ") == "900"


def test_extract_macro_args_basic():
    args = extract_macro_args("OBJECT(a, b, c),", "OBJECT")
    assert args == ["a", "b", "c"]


def test_extract_macro_args_strips_comments():
    line = "MACRO_OBJECT(/*preset*/ macro_goomba, /*yaw*/ 0, /*pos*/ 1, 2, 3),"
    assert extract_macro_args(line, "MACRO_OBJECT") == [
        "macro_goomba",
        "0",
        "1",
        "2",
        "3",
    ]


def test_extract_macro_args_preserves_nested_parens():
    line = "OBJECT(MODEL_NONE, 0, BPARAM2(41), bhvPoleGrabbing),"
    assert extract_macro_args(line, "OBJECT") == [
        "MODEL_NONE",
        "0",
        "BPARAM2(41)",
        "bhvPoleGrabbing",
    ]


def test_extract_macro_args_requires_exact_macro_name():
    # OBJECT must not match OBJECT_WITH_ACTS.
    assert extract_macro_args("OBJECT_WITH_ACTS(a, b)", "OBJECT") is None


def test_extract_macro_args_returns_none_for_other_lines():
    assert extract_macro_args("RETURN(),", "OBJECT") is None


def test_parse_c_enum_auto_increment():
    text = "enum E {\n    A,\n    B,\n    C\n};\n"
    assert parse_c_enum(text, "E") == [("A", 0), ("B", 1), ("C", 2)]


def test_parse_c_enum_explicit_values_and_references():
    text = (
        "enum E {\n"
        "    NONE = -1,\n"  # negative, then auto-increment continues from it
        "    ZERO,\n"  # 0
        "    HEX = 0x65,\n"  # explicit hex
        "    NEXT,\n"  # 0x66
        "    ALIAS = ZERO,\n"  # reference to an earlier member
        "};\n"
    )
    values = dict(parse_c_enum(text, "E"))
    assert values["NONE"] == -1
    assert values["ZERO"] == 0
    assert values["HEX"] == 0x65
    assert values["NEXT"] == 0x66
    assert values["ALIAS"] == 0


def test_parse_c_enum_ignores_other_enums():
    text = "enum Other {\n X\n};\nenum Wanted {\n Y\n};\n"
    assert parse_c_enum(text, "Wanted") == [("Y", 0)]
