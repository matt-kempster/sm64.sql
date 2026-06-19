"""Unit tests for the native-C behavior-call parser (tree-sitter based).

These build a tiny fake decomp tree on disk so the reachability attribution can
be exercised without a full checkout.
"""

from pathlib import Path
from typing import Dict, List

from sm64_sql.behavior_call import parse_behavior_calls, parse_c_functions


def _behaviors_dir(tmp_path: Path) -> Path:
    d = tmp_path / "src" / "game" / "behaviors"
    d.mkdir(parents=True)
    return d


def test_parse_c_functions_finds_defs_and_calls(tmp_path: Path):
    src = tmp_path / "f.c"
    src.write_text(
        "void *make_thing(s32 n) {\n"  # pointer-returning function
        "    return spawn_object(o, MODEL_STAR, bhvStar);\n"
        "}\n"
        "void plain(void) {\n"
        "    s32 x = (s32)(o->oForwardVel);\n"  # cast shaped like a call
        "}\n"
    )
    funcs = {f.name: f for f in parse_c_functions(src, "f.c")}
    assert set(funcs) == {"make_thing", "plain"}
    # The cast "(s32)(...)" is not recorded as a call; only the real spawn is.
    assert [c.callee for c in funcs["make_thing"].calls] == ["spawn_object"]
    assert funcs["make_thing"].calls[0].args == ["o", "MODEL_STAR", "bhvStar"]
    assert [c.callee for c in funcs["plain"].calls] == []


def test_multiline_call_is_captured(tmp_path: Path):
    src = tmp_path / "f.c"
    src.write_text(
        "void loop(void) {\n"
        "    spawn_object_relative(\n"
        "        0, 0, 0,\n"
        "        o, MODEL_STAR,\n"
        "        bhvStar);\n"
        "}\n"
    )
    (fn,) = parse_c_functions(src, "f.c")
    (call,) = fn.calls
    assert call.callee == "spawn_object_relative"
    # tree-sitter splits the argument list structurally, across lines.
    assert call.args[-2:] == ["MODEL_STAR", "bhvStar"]


def test_reachability_attributes_helpers_to_behavior(tmp_path: Path):
    _behaviors_dir(tmp_path).joinpath("thing.inc.c").write_text(
        "void thing_helper(void) {\n"
        "    spawn_object(o, MODEL_SMOKE, bhvSmoke);\n"
        "}\n"
        "void bhv_thing_loop(void) {\n"
        "    cur_obj_play_sound_2(SOUND_GENERAL_COIN);\n"
        "    thing_helper();\n"
        "}\n"
    )
    roots: Dict[str, List[str]] = {"bhv_thing_loop": ["bhvThing"]}
    rows = parse_behavior_calls(tmp_path, roots)

    # Every call is attributed to bhvThing, including the spawn made two levels
    # deep inside the helper the loop calls.
    assert {r.behavior_name for r in rows} == {"bhvThing"}
    spawns = [r for r in rows if r.call == "spawn_object"]
    assert len(spawns) == 1
    assert spawns[0].function == "thing_helper"
    assert spawns[0].file == "src/game/behaviors/thing.inc.c"
    assert {r.call for r in rows} == {
        "cur_obj_play_sound_2",
        "thing_helper",
        "spawn_object",
    }


def test_shared_helper_attributed_to_every_caller(tmp_path: Path):
    _behaviors_dir(tmp_path).joinpath("shared.inc.c").write_text(
        "void make_respawner(void) {\n"
        "    spawn_object(o, MODEL_NONE, bhvRespawner);\n"
        "}\n"
        "void bhv_a_loop(void) { make_respawner(); }\n"
        "void bhv_b_loop(void) { make_respawner(); }\n"
    )
    roots = {"bhv_a_loop": ["bhvA"], "bhv_b_loop": ["bhvB"]}
    rows = parse_behavior_calls(tmp_path, roots)
    # The shared helper's spawn is attributed to both behaviors that reach it.
    respawner = {r.behavior_name for r in rows if r.call == "spawn_object"}
    assert respawner == {"bhvA", "bhvB"}


def test_external_root_outside_behaviors_dir(tmp_path: Path):
    # A behaviors/ file exists (so the dir is present) but the root lives in a
    # menu file, like the real act-selector / menu-button behaviors.
    _behaviors_dir(tmp_path).joinpath("placeholder.inc.c").write_text(
        "void bhv_placeholder(void) {}\n"
    )
    menu = tmp_path / "src" / "menu"
    menu.mkdir(parents=True)
    menu.joinpath("star_select.c").write_text(
        "void bhv_act_selector_loop(void) {\n"
        "    cur_obj_play_sound_2(SOUND_MENU_CLICK);\n"
        "}\n"
    )
    roots = {"bhv_act_selector_loop": ["bhvActSelector"]}
    rows = parse_behavior_calls(tmp_path, roots)
    # The external root's direct call is captured and attributed.
    assert any(
        r.behavior_name == "bhvActSelector"
        and r.call == "cur_obj_play_sound_2"
        and r.file == "src/menu/star_select.c"
        for r in rows
    )


def test_unparsed_root_is_skipped(tmp_path: Path):
    # A CALL_NATIVE root with no definition anywhere (e.g. a macro template, or
    # an engine helper used directly as a loop) simply contributes no rows.
    _behaviors_dir(tmp_path).joinpath("thing.inc.c").write_text(
        "void bhv_thing_loop(void) { cur_obj_play_sound_2(SOUND_GENERAL_COIN); }\n"
    )
    roots = {"bhv_thing_loop": ["bhvThing"], "func": ["bhvBogus"]}
    rows = parse_behavior_calls(tmp_path, roots)
    assert {r.behavior_name for r in rows} == {"bhvThing"}
