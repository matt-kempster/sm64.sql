from sm64_sql.macro_preset import get_macro_preset_names, parse_macro_presets

MACRO_PRESETS_H = """\
#ifndef MACRO_PRESETS_H
#define MACRO_PRESETS_H

enum MacroPresets {
    macro_yellow_coin_1,
    macro_yellow_coin_2,
    macro_coin_line_horizontal,

    macro_count
};

#endif // MACRO_PRESETS_H
"""

MACRO_PRESETS_INC_C = """\
#include "macro_presets.h"

struct MacroPreset {
    const BehaviorScript *behavior;
    s16 model;
    s16 param;
};

static struct MacroPreset sMacroObjectPresets[] = {
    /* macro_yellow_coin_1        */ { bhvYellowCoin, MODEL_YELLOW_COIN, 0 },
    /* macro_yellow_coin_2        */ { bhvOneCoin, MODEL_YELLOW_COIN, 0 }, // unused
    /* macro_coin_line_horizontal */ { bhvCoinFormation, MODEL_NONE, COIN_FORMATION_BP_LINE_HORIZONTAL | COIN_FORMATION_BP_FLAG_FLYING },
};
"""


def _write(tmp_path):
    names = tmp_path / "macro_presets.h"
    data = tmp_path / "macro_presets.inc.c"
    names.write_text(MACRO_PRESETS_H)
    data.write_text(MACRO_PRESETS_INC_C)
    return data, names


def test_get_macro_preset_names_skips_sentinel(tmp_path):
    names_path = tmp_path / "macro_presets.h"
    names_path.write_text(MACRO_PRESETS_H)
    names = get_macro_preset_names(names_path)
    assert names == [
        "macro_yellow_coin_1",
        "macro_yellow_coin_2",
        "macro_coin_line_horizontal",
    ]
    assert "macro_count" not in names


def test_parse_macro_presets(tmp_path):
    data, names = _write(tmp_path)
    presets = parse_macro_presets(data, names)
    assert len(presets) == 3

    first = presets[0]
    assert first.macro_name == "macro_yellow_coin_1"
    assert first.behavior == "bhvYellowCoin"
    assert first.model_name == "MODEL_YELLOW_COIN"
    assert first.param == "0"
    assert first.param_value == 0

    # A `// unused` line comment must not break parsing.
    assert presets[1].macro_name == "macro_yellow_coin_2"
    assert presets[1].behavior == "bhvOneCoin"

    # A `|`-joined param expression stays in one field, so the row still has
    # exactly three columns; the symbolic value is kept but not resolved.
    assert presets[2].macro_name == "macro_coin_line_horizontal"
    assert presets[2].model_name == "MODEL_NONE"
    assert presets[2].param == (
        "COIN_FORMATION_BP_LINE_HORIZONTAL | COIN_FORMATION_BP_FLAG_FLYING"
    )
    assert presets[2].param_value is None
