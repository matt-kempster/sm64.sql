"""Unit tests for the Mario action-state-machine parser (tree-sitter based).

These build a tiny fake decomp tree on disk -- an include/sm64.h with a handful
of ACT_* constants and a src/game/ with a dispatcher switch, a few handlers, and
the transition setters -- so the constant decoding, the switch/fall-through
handler mapping, the reachability attribution, and the residue can all be
exercised without a full checkout.
"""

from pathlib import Path

from sm64_sql.mario_action import parse_mario_actions

_HEADER = """\
#define ACT_ID_MASK 0x000001FF
#define ACT_GROUP_MASK       0x000001C0
#define ACT_GROUP_STATIONARY /* 0x00000000 */ (0 << 6)
#define ACT_GROUP_MOVING     /* 0x00000040 */ (1 << 6)
#define ACT_GROUP_AIRBORNE   /* 0x00000080 */ (2 << 6)
#define ACT_FLAG_STATIONARY  /* 0x00000200 */ (1 <<  9)
#define ACT_FLAG_MOVING      /* 0x00000400 */ (1 << 10)
#define ACT_FLAG_AIR         /* 0x00000800 */ (1 << 11)
#define ACT_UNINITIALIZED    0x00000000 // (0x000)
#define ACT_IDLE             0x00000201 // stationary
#define ACT_WALKING          0x04000440 // moving
#define ACT_DECELERATING     0x04000441 // moving
#define ACT_BRAKING          0x04000443 // moving
#define ACT_TURNING_AROUND   0x04000442 // moving
#define ACT_STEEP_JUMP       0x03000888 // airborne
"""

# set_mario_action / drop_and_set_mario_action are the leaf setters (never
# recursed); set_steep_jump_action is a fixed-target helper that IS recursed.
# Note set_mario_action's body sets ACT_TURNING_AROUND internally -- a caller
# must NOT inherit that edge, since the setter is a leaf.
_MARIO_C = """\
u32 set_mario_action(struct MarioState *m, u32 action, u32 actionArg) {
    set_mario_action(m, ACT_TURNING_AROUND, 0);
    m->action = action;
    return TRUE;
}

s32 drop_and_set_mario_action(struct MarioState *m, u32 action, u32 actionArg) {
    return set_mario_action(m, action, actionArg);
}

void set_steep_jump_action(struct MarioState *m) {
    drop_and_set_mario_action(m, ACT_STEEP_JUMP, 0);
}
"""

_MOVING_C = """\
s32 common_moving_cancels(struct MarioState *m) {
    set_mario_action(m, ACT_IDLE, 0);
    return FALSE;
}

s32 act_walking(struct MarioState *m) {
    if (x) {
        set_mario_action(m, ACT_DECELERATING, 0);
    }
    common_moving_cancels(m);
    set_steep_jump_action(m);
    return FALSE;
}

s32 act_decelerating(struct MarioState *m) {
    u32 endAction = ACT_WALKING;
    set_mario_action(m, endAction, 0);
    return FALSE;
}

s32 act_turning_around(struct MarioState *m) {
    return FALSE;
}

s32 mario_execute_moving_action(struct MarioState *m) {
    s32 cancel;
    switch (m->action) {
        case ACT_WALKING:        cancel = act_walking(m);        break;
        case ACT_DECELERATING:   cancel = act_decelerating(m);   break;
        case ACT_BRAKING:
        case ACT_TURNING_AROUND: cancel = act_turning_around(m); break;
    }
    return cancel;
}
"""


def _fake_repo(tmp_path: Path) -> Path:
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "sm64.h").write_text(_HEADER)
    game = tmp_path / "src" / "game"
    game.mkdir(parents=True)
    (game / "mario.c").write_text(_MARIO_C)
    (game / "mario_actions_moving.c").write_text(_MOVING_C)
    return tmp_path


def test_action_constants_decoded(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    nodes = {a.action_name: a for a in parsed.actions}
    # The masks/groups/flags are not actions; every real ACT_* is a node.
    assert set(nodes) == {
        "ACT_UNINITIALIZED",
        "ACT_IDLE",
        "ACT_WALKING",
        "ACT_DECELERATING",
        "ACT_BRAKING",
        "ACT_TURNING_AROUND",
        "ACT_STEEP_JUMP",
    }
    walking = nodes["ACT_WALKING"]
    assert walking.id == "0x04000440"
    assert walking.group_name == "MOVING"
    assert walking.flags_json == '["MOVING"]'
    assert walking.handler == "act_walking"
    assert walking.file == "src/game/mario_actions_moving.c"
    # ACT_STEEP_JUMP is airborne, has the AIR flag, and (not in the switch) no handler.
    steep = nodes["ACT_STEEP_JUMP"]
    assert steep.group_name == "AIRBORNE"
    assert steep.flags_json == '["AIR"]'
    assert steep.handler is None and steep.file is None
    # ACT_UNINITIALIZED (value 0) has neither group nor flags nor handler.
    uninit = nodes["ACT_UNINITIALIZED"]
    assert uninit.group_name is None and uninit.flags_json == "[]"
    assert uninit.handler is None


def test_fall_through_case_shares_handler(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    nodes = {a.action_name: a for a in parsed.actions}
    # ACT_BRAKING falls through to ACT_TURNING_AROUND, so both run that handler.
    assert nodes["ACT_BRAKING"].handler == "act_turning_around"
    assert nodes["ACT_TURNING_AROUND"].handler == "act_turning_around"


def test_reachability_and_setter_leaf(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    names = {a.action_name for a in parsed.actions}
    edges = {(c.action_name, c.target) for c in parsed.calls if c.target in names}
    # Direct transition in the handler body.
    assert ("ACT_WALKING", "ACT_DECELERATING") in edges
    # Through a shared helper (common_moving_cancels).
    assert ("ACT_WALKING", "ACT_IDLE") in edges
    # Through a fixed-target helper that is recursed into (set_steep_jump_action
    # -> drop_and_set_mario_action(ACT_STEEP_JUMP)).
    assert ("ACT_WALKING", "ACT_STEEP_JUMP") in edges
    # NEGATIVE: set_mario_action's own body sets ACT_TURNING_AROUND, but the
    # setter is a leaf (never recursed), so no caller inherits that edge.
    assert ("ACT_WALKING", "ACT_TURNING_AROUND") not in edges
    # A terminal action has no outgoing transitions.
    assert not any(src == "ACT_TURNING_AROUND" for src, _ in edges)


def test_forwarded_target_is_residue(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    names = {a.action_name for a in parsed.actions}
    # act_decelerating sets a forwarded local (endAction), not a literal action:
    # it is captured in the backbone but is not a resolved edge.
    residue = {c.target for c in parsed.calls if c.target and c.target not in names}
    assert "endAction" in residue
    assert ("ACT_DECELERATING", "endAction") in {
        (c.action_name, c.target) for c in parsed.calls
    }
