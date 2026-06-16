from sm64_sql.warp import parse_warps

SCRIPT_C = """\
    WARP_NODE(/*id*/ WARP_NODE_GLOBAL, /*destLevel*/ LEVEL_CASTLE, /*destArea*/ 1, /*destNode*/ WARP_NODE_00, /*flags*/ WARP_NO_CHECKPOINT),
    AREA(/*index*/ 1, bob_geo_000488),
        OBJECT(/*model*/ MODEL_NONE, /*pos*/ 0, 0, 0, /*angle*/ 0, 0, 0, /*bhvParam*/ 0, /*bhv*/ bhvWarp),
        WARP_NODE(/*id*/ WARP_NODE_0A, /*destLevel*/ LEVEL_BOB, /*destArea*/ 1, /*destNode*/ WARP_NODE_0A, /*flags*/ WARP_NO_CHECKPOINT),
        WARP_NODE(/*id*/ WARP_NODE_SUCCESS, /*destLevel*/ LEVEL_CASTLE, /*destArea*/ 1, /*destNode*/ WARP_NODE_32, /*flags*/ WARP_NO_CHECKPOINT),
        INSTANT_WARP(/*index*/ 2, /*destArea*/ 3, /*displace*/ 10240, 7168, -10240),
    END_AREA(),
    AREA(/*index*/ 2, bob_geo_other),
        PAINTING_WARP_NODE(/*id*/ WARP_NODE_PAINTING, /*destLevel*/ LEVEL_BOB, /*destArea*/ 1, /*destNode*/ WARP_NODE_0A, /*flags*/ WARP_NO_CHECKPOINT),
    END_AREA(),
"""


def test_parse_warps(tmp_path):
    path = tmp_path / "script.c"
    path.write_text(SCRIPT_C)
    warps, instant_warps = parse_warps(path, "bob")

    assert len(warps) == 4  # 1 global + 2 in-area WARP_NODE + 1 PAINTING_WARP_NODE
    assert len(instant_warps) == 1

    by_node = {w.node_id: w for w in warps}
    # A warp before the first AREA() is level-global (area 0).
    assert by_node["WARP_NODE_GLOBAL"].area == 0
    success = by_node["WARP_NODE_SUCCESS"]
    assert success.area == 1  # picked up the enclosing AREA(1)
    assert success.dest_level == "LEVEL_CASTLE"
    assert success.dest_area == 1
    assert success.dest_node == "WARP_NODE_32"
    assert success.flags == "WARP_NO_CHECKPOINT"
    assert success.is_painting is False

    # The painting warp is in area 2 and flagged.
    painting = by_node["WARP_NODE_PAINTING"]
    assert painting.area == 2
    assert painting.is_painting is True

    # Instant warps capture index, destination area, and displacement.
    iw = instant_warps[0]
    assert iw.area == 1
    assert iw.warp_index == 2
    assert iw.dest_area == 3
    assert (iw.displace_x, iw.displace_y, iw.displace_z) == (10240, 7168, -10240)
