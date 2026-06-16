from sm64_sql.behavior_param import parse_behavior_param


def test_plain_zero():
    p = parse_behavior_param("0")
    assert p.raw == "0"
    assert p.value == 0
    assert (p.param1, p.param2, p.param3, p.param4) == (None, None, None, None)


def test_empty_defaults_to_zero():
    p = parse_behavior_param("")
    assert p.raw == "0"
    assert p.value == 0


def test_single_numeric_bparam_slot_resolves():
    p = parse_behavior_param("BPARAM2(184)")
    assert p.param2 == "184"
    assert (p.param1, p.param3, p.param4) == (None, None, None)
    assert p.value == 184 << 16


def test_two_numeric_bparam_slots_combine():
    p = parse_behavior_param("BPARAM1(0x08) | BPARAM2(0xA5)")
    assert p.param1 == "0x08"
    assert p.param2 == "0xA5"
    assert p.value == (0x08 << 24) | (0xA5 << 16)


def test_symbolic_slot_keeps_symbol_but_no_value():
    p = parse_behavior_param("BPARAM2(WARP_NODE_0A)")
    assert p.param2 == "WARP_NODE_0A"
    assert p.value is None


def test_mixed_numeric_and_symbolic_value_is_none_slots_kept():
    p = parse_behavior_param("BPARAM1(0x01) | BPARAM2(WARP_NODE_03)")
    assert p.param1 == "0x01"
    assert p.param2 == "WARP_NODE_03"
    # One symbolic operand means the combined value cannot be resolved.
    assert p.value is None


def test_bare_symbol_is_kept_without_slots():
    p = parse_behavior_param("DIALOG_089")
    assert p.raw == "DIALOG_089"
    assert p.value is None
    assert (p.param1, p.param2, p.param3, p.param4) == (None, None, None, None)


def test_bare_hex_resolves():
    p = parse_behavior_param("0x40")
    assert p.value == 0x40


def test_or_of_symbols_unresolved():
    p = parse_behavior_param(
        "COIN_FORMATION_BP_LINE_HORIZONTAL | COIN_FORMATION_BP_FLAG_FLYING"
    )
    assert p.value is None
    assert "|" in p.raw


def test_whitespace_is_normalized():
    p = parse_behavior_param("BPARAM1(0x08)  |   BPARAM2(0xA6)")
    assert p.raw == "BPARAM1(0x08) | BPARAM2(0xA6)"
