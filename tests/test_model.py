from sm64_sql.model import parse_model_ids

MODEL_IDS_H = """\
#ifndef MODEL_IDS_H
#define MODEL_IDS_H

#define MODEL_NONE 0x00
#define MODEL_LEVEL_GEOMETRY_0D 0x0D
#define MODEL_MARIO 1
// an alias of an earlier id (level geometry override)
#define MODEL_WF_GIANT_POLE MODEL_LEVEL_GEOMETRY_0D
// an unresolved reference should be skipped, not emitted with a wrong id
#define MODEL_MYSTERY SOME_UNKNOWN_SYMBOL

#endif // MODEL_IDS_H
"""


def test_parse_model_ids_resolves_and_skips(tmp_path):
    path = tmp_path / "model_ids.h"
    path.write_text(MODEL_IDS_H)

    models = parse_model_ids(path)
    by_name = {m.model_name: m.model_id for m in models}

    assert by_name["MODEL_NONE"] == 0x00
    assert by_name["MODEL_MARIO"] == 1
    assert by_name["MODEL_LEVEL_GEOMETRY_0D"] == 0x0D
    # The alias resolves to the referenced id, not a stale previous value.
    assert by_name["MODEL_WF_GIANT_POLE"] == 0x0D
    # The unresolved reference and the include guard are not emitted.
    assert "MODEL_MYSTERY" not in by_name
    assert "MODEL_IDS_H" not in by_name
