from sm64_sql.parse_utils import (
    extract_macro_args,
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
