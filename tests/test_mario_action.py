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
#define ACT_FREEFALL         0x00000882 // airborne
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

s32 common_land_step(struct MarioState *m, u32 landAction) {
    return set_mario_action(m, landAction, 0);
}

s32 act_decelerating(struct MarioState *m) {
    u32 endAction = ACT_WALKING;
    set_mario_action(m, endAction, 0);
    if (m->input & INPUT_A_PRESSED) {
        common_land_step(m, ACT_FREEFALL);
    }
    set_mario_action(m, x ? ACT_BRAKING : ACT_IDLE, 0);
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


# --- flag-gated transitions (the backflip -> hanging false-edge class) ---------
# perform_air_step returns AIR_STEP_GRABBED_CEILING only when the caller passes
# AIR_STEP_CHECK_HANG, and AIR_STEP_GRABBED_LEDGE only with
# AIR_STEP_CHECK_LEDGE_GRAB. common_air_action_step switches on that result, so
# its ceiling/ledge transitions are only real for callers that pass the flag.
_GATE_HEADER = """\
#define ACT_GROUP_MASK     0x000001C0
#define ACT_GROUP_AIRBORNE /* 0x00000080 */ (2 << 6)
#define ACT_FLAG_AIR       /* 0x00000800 */ (1 << 11)
#define ACT_HANG      0x00000880 // airborne
#define ACT_LEDGE     0x00000881 // airborne
#define ACT_LAND      0x00000882 // airborne
#define ACT_FLAGGED   0x00000883 // airborne (passes both flags)
#define ACT_PLAIN     0x00000884 // airborne (passes no flags)
#define ACT_SELF      0x00000885 // airborne (passes the flag itself)
"""

_GATE_MARIO_C = """\
u32 set_mario_action(struct MarioState *m, u32 action, u32 actionArg) {
    m->action = action;
    return TRUE;
}
"""

_GATE_STEP_C = """\
u32 perform_air_step(struct MarioState *m, u32 stepArg) {
    if ((stepArg & AIR_STEP_CHECK_HANG) && m->ceil != NULL) {
        return AIR_STEP_GRABBED_CEILING;
    }
    if ((stepArg & AIR_STEP_CHECK_LEDGE_GRAB) && m->wall != NULL) {
        return AIR_STEP_GRABBED_LEDGE;
    }
    return AIR_STEP_NONE;
}
"""

_GATE_AIRBORNE_C = """\
u32 common_air_action_step(struct MarioState *m, u32 landAction, u32 stepArg) {
    switch (perform_air_step(m, stepArg)) {
        case AIR_STEP_LANDED:
            set_mario_action(m, landAction, 0);
            break;
        case AIR_STEP_GRABBED_LEDGE:
            set_mario_action(m, ACT_LEDGE, 0);
            break;
        case AIR_STEP_GRABBED_CEILING:
            set_mario_action(m, ACT_HANG, 0);
            break;
    }
    return 0;
}

s32 act_flagged(struct MarioState *m) {
    common_air_action_step(m, ACT_LAND, AIR_STEP_CHECK_LEDGE_GRAB | AIR_STEP_CHECK_HANG);
    return FALSE;
}

s32 act_plain(struct MarioState *m) {
    common_air_action_step(m, ACT_LAND, 0);
    return FALSE;
}

s32 act_self(struct MarioState *m) {
    switch (perform_air_step(m, AIR_STEP_CHECK_LEDGE_GRAB)) {
        case AIR_STEP_GRABBED_LEDGE:
            set_mario_action(m, ACT_LEDGE, 0);
            break;
    }
    return FALSE;
}

s32 mario_execute_airborne_action(struct MarioState *m) {
    s32 cancel;
    switch (m->action) {
        case ACT_FLAGGED: cancel = act_flagged(m); break;
        case ACT_PLAIN:   cancel = act_plain(m);   break;
        case ACT_SELF:    cancel = act_self(m);    break;
    }
    return cancel;
}
"""


def _gate_repo(tmp_path: Path) -> Path:
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "sm64.h").write_text(_GATE_HEADER)
    game = tmp_path / "src" / "game"
    game.mkdir(parents=True)
    (game / "mario.c").write_text(_GATE_MARIO_C)
    (game / "mario_actions_airborne.c").write_text(_GATE_AIRBORNE_C)
    (game / "mario_step.c").write_text(_GATE_STEP_C)
    return tmp_path


def test_flag_gated_transition_refuted_and_kept(tmp_path: Path):
    from sm64_sql.mario_action import _return_gate_map

    repo = _gate_repo(tmp_path)
    # The gate contract is discovered from the code, not hardcoded; AIR_STEP_NONE
    # is also returned ungated, so it is correctly NOT treated as gated.
    assert _return_gate_map(repo) == {
        "AIR_STEP_GRABBED_CEILING": "AIR_STEP_CHECK_HANG",
        "AIR_STEP_GRABBED_LEDGE": "AIR_STEP_CHECK_LEDGE_GRAB",
    }

    parsed = parse_mario_actions(repo)
    names = {a.action_name for a in parsed.actions}
    live = {(c.action_name, c.target) for c in parsed.calls if not c.gated_by}
    gated = {(c.action_name, c.target): c.gated_by for c in parsed.calls if c.gated_by}

    # The caller that passes the flags reaches both gated cases.
    assert ("ACT_FLAGGED", "ACT_HANG") in live
    assert ("ACT_FLAGGED", "ACT_LEDGE") in live
    # The caller that passes neither is refuted on both -- the false edges.
    assert ("ACT_PLAIN", "ACT_HANG") not in live
    assert ("ACT_PLAIN", "ACT_LEDGE") not in live
    assert gated[("ACT_PLAIN", "ACT_HANG")] == "AIR_STEP_CHECK_HANG"
    assert gated[("ACT_PLAIN", "ACT_LEDGE")] == "AIR_STEP_CHECK_LEDGE_GRAB"
    # A handler that passes the flag itself (no forwarding) keeps its edge.
    assert ("ACT_SELF", "ACT_LEDGE") in live
    # Refuted rows stay on the backbone (auditable), with a literal target.
    assert ("ACT_PLAIN", "ACT_HANG") in {
        (c.action_name, c.target) for c in parsed.calls
    }
    assert "ACT_HANG" in names


# --- dispatcher-level group cancels (the ACT_DROWNING orphan class) -----------
# A per-group dispatcher runs check_common_*_cancels BEFORE its switch, so those
# transitions apply to every action in the group, not to one handler.
_CANCEL_HEADER = """\
#define ACT_GROUP_MASK      0x000001C0
#define ACT_GROUP_SUBMERGED /* 0x000000C0 */ (3 << 6)
#define ACT_SWIM      0x000000C0 // submerged
#define ACT_FLUTTER   0x000000C1 // submerged
#define ACT_DROWN     0x300000C2 // submerged
"""

_CANCEL_MARIO_C = """\
u32 set_mario_action(struct MarioState *m, u32 action, u32 actionArg) {
    m->action = action;
    return TRUE;
}
"""

_CANCEL_SUBMERGED_C = """\
s32 check_common_submerged_cancels(struct MarioState *m) {
    if (m->pos[1] > m->waterLevel - 80) {
        set_mario_action(m, ACT_DROWN, 0);
    }
    return FALSE;
}

s32 act_swim(struct MarioState *m) {
    return FALSE;
}

s32 act_flutter(struct MarioState *m) {
    return FALSE;
}

s32 act_drown(struct MarioState *m) {
    return FALSE;
}

s32 mario_execute_submerged_action(struct MarioState *m) {
    s32 cancel;
    if (check_common_submerged_cancels(m)) {
        return TRUE;
    }
    switch (m->action) {
        case ACT_SWIM:    cancel = act_swim(m);    break;
        case ACT_FLUTTER: cancel = act_flutter(m); break;
        case ACT_DROWN:   cancel = act_drown(m);   break;
    }
    return cancel;
}
"""


def _cancel_repo(tmp_path: Path) -> Path:
    (tmp_path / "include").mkdir()
    (tmp_path / "include" / "sm64.h").write_text(_CANCEL_HEADER)
    game = tmp_path / "src" / "game"
    game.mkdir(parents=True)
    (game / "mario.c").write_text(_CANCEL_MARIO_C)
    (game / "mario_actions_submerged.c").write_text(_CANCEL_SUBMERGED_C)
    return tmp_path


def test_dispatcher_cancel_is_attributed_group_wide(tmp_path: Path):
    parsed = parse_mario_actions(_cancel_repo(tmp_path))
    names = {a.action_name for a in parsed.actions}
    edges = {(c.action_name, c.target) for c in parsed.calls if c.target in names}
    # The cancel runs in the dispatcher before the switch, so every dispatched
    # action -- not just one handler -- can transition to ACT_DROWN, including
    # ACT_DROWN itself (it stays submerged until the water level drops).
    assert ("ACT_SWIM", "ACT_DROWN") in edges
    assert ("ACT_FLUTTER", "ACT_DROWN") in edges
    assert ("ACT_DROWN", "ACT_DROWN") in edges
    # The empty drowning handler emits nothing of its own.
    assert not any(src == "ACT_DROWN" and tgt != "ACT_DROWN" for src, tgt in edges)


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
        "ACT_FREEFALL",
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


def test_guard_conditions_mined(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    cond = {(c.action_name, c.target): c.condition for c in parsed.calls}
    # The conditional transition in act_walking carries its enclosing if-guard.
    assert cond[("ACT_WALKING", "ACT_DECELERATING")] == "x"
    # The shared-helper transition (set_mario_action(ACT_IDLE)) is unguarded.
    assert cond[("ACT_WALKING", "ACT_IDLE")] is None
    # A forwarded data transition takes its guard from the *caller's* call site.
    dt = {(d.action_name, d.to_action): d for d in parsed.data_transitions}
    assert (
        dt[("ACT_DECELERATING", "ACT_FREEFALL")].condition
        == "m->input & INPUT_A_PRESSED"
    )


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


def test_data_transitions_resolve_forwarded_and_expr(tmp_path: Path):
    parsed = parse_mario_actions(_fake_repo(tmp_path))
    dt = {(d.action_name, d.to_action): d for d in parsed.data_transitions}
    # Forwarded parameter: act_decelerating calls common_land_step(m, ACT_FREEFALL),
    # which does set_mario_action(m, landAction) -- resolved from the call site.
    assert ("ACT_DECELERATING", "ACT_FREEFALL") in dt
    assert dt[("ACT_DECELERATING", "ACT_FREEFALL")].source == "landAction"
    # Ternary: both branches of (x ? ACT_BRAKING : ACT_IDLE) are real transitions.
    assert ("ACT_DECELERATING", "ACT_BRAKING") in dt
    assert ("ACT_DECELERATING", "ACT_IDLE") in dt
    assert dt[("ACT_DECELERATING", "ACT_BRAKING")].source == "expr"
    # The unresolved local (endAction) is NOT promoted to a resolved edge.
    assert ("ACT_DECELERATING", "ACT_WALKING") not in dt
    # Data transitions never duplicate a literal edge: ACT_WALKING -> ACT_IDLE is
    # already literal (via common_moving_cancels), so it is not re-emitted here.
    assert ("ACT_WALKING", "ACT_IDLE") not in dt
