# sm64.sql

Load [Super Mario 64 decompilation](https://github.com/n64decomp/sm64) game
data into a SQLite database so you can explore it with SQL.

The decomp stores level contents as C macros and tables (`OBJECT(...)`,
`MACRO_OBJECT(...)`, `enum MacroPresets`, `#define MODEL_*`, ...). `sm64.sql`
reads those source files and writes the equivalent rows into a SQLite database,
so questions like "which objects appear only in act 1?" or "what model does each
macro preset use?" become one-line queries.

## Install

```sh
pip install -e .            # from a checkout
pip install -e ".[dev]"     # plus pytest / black / mypy for development
```

Requires Python 3.8+ and a checkout of the SM64 decompilation source (this tool
reads the source; it does not need the game to be built).

## Usage

```sh
sm64-sql --repo /path/to/sm64 --db sm64.db
# or, without installing:
PYTHONPATH=src python -m sm64_sql --repo /path/to/sm64 --db sm64.db
```

| Flag | Description |
| --- | --- |
| `-r`, `--repo` | Path to the SM64 decompilation source tree (required). |
| `-d`, `--db` | SQLite file to write. Omit to use an in-memory database. |
| `-o`, `--overwrite` | Overwrite an existing database without prompting. |

## Schema

| Table | Source | Columns |
| --- | --- | --- |
| `object` | `levels/*/script.c` | `model_name`, `level`, `initial_x/y/z`, `initial_rot_x/y/z`, `behavior`, `in_act_1` … `in_act_6` |
| `macro_object` | `levels/**/macro.inc.c` | `macro_name`, `level`, `yaw`, `pos_x/y/z` |
| `model` | `include/model_ids.h` | `model_name`, `model_id` |
| `macro_preset` | `include/macro_presets.h` + `macro_presets.inc.c` | `macro_name`, `behavior`, `model_name` |
| `level` | `levels/level_defines.h` | `level_name`, `course_name`, `folder`, `internal_name`, `is_stub` |
| `course` | `levels/course_defines.h` | `course_name`, `display_name`, `dance_cutscene`, `is_bonus` |
| `sequence` | `include/seq_ids.h` | `seq_name`, `seq_id` (music tracks) |
| `dialog` | `text/us/dialogs.h` + `include/dialog_ids.h` | `dialog_name`, `dialog_id`, `lines_per_box`, `left_offset`, `width`, `text` |
| `special_preset` | `include/special_presets.h` + `special_presets.inc.c` | `preset_name`, `preset_id`, `preset_type`, `default_param`, `model_name`, `behavior` |
| `special_object` | `levels/**/collision.inc.c` | `preset_name`, `level`, `area`, `pos_x/y/z`, `yaw` |

Names such as `MODEL_BOO`, `bhvGoomba`, and `macro_yellow_coin_2` are kept as
the symbolic strings used in the source, so the tables join naturally on those
names.

## Example queries

```sql
-- How many placed objects are in each level?
SELECT level, COUNT(*) AS n FROM object GROUP BY level ORDER BY n DESC;

-- Objects that only appear during act 1.
SELECT level, behavior, initial_x, initial_y, initial_z
FROM object
WHERE in_act_1 AND NOT (in_act_2 OR in_act_3 OR in_act_4 OR in_act_5 OR in_act_6);

-- Join placed objects to their numeric model id.
SELECT o.level, o.behavior, m.model_id
FROM object o JOIN model m ON o.model_name = m.model_name;

-- Which behavior/model does each macro object resolve to?
SELECT mo.level, mo.macro_name, mp.behavior, mp.model_name
FROM macro_object mo JOIN macro_preset mp ON mo.macro_name = mp.macro_name;
```

## How it works

The decomp's level data is written as C *macro invocations* with symbolic
arguments (`OBJECT(MODEL_BOO, ..., bhvGhostHuntBigBoo)`), not plain C that a
compiler would parse directly — the files are designed to be `#include`d and
macro-expanded. `sm64.sql` reads them line by line and pulls the arguments out
of each known macro call. Argument extraction is bracket-aware
(`src/sm64_sql/parse_utils.py`), so behavior-parameter expressions like
`BPARAM2(41)` or `BPARAM1(0) | BPARAM2(1)` are handled correctly.

This deliberately stops at *structure*, not *semantics*: it keeps `MODEL_BOO`
as a string rather than expanding it to a number. See
[`docs/parsing.md`](docs/parsing.md) for the trade-offs and when a real C
parser (e.g. tree-sitter) would be worth adopting.

## Development

```sh
pip install -e ".[dev]"
pytest                 # unit tests (fast, hermetic)
SM64_DECOMP_PATH=/path/to/sm64 pytest   # also run the end-to-end test
black src tests        # format
mypy                   # type-check
```

## Status & limitations

Implemented: objects, macro objects, models, and macro presets, verified to
parse a full current `n64decomp/sm64` checkout with every row accounted for.

Not yet captured (contributions welcome):

- Behavior parameters (`bhvParam` / preset `param`) are parsed past but not
  stored.
- Behaviors, geo layouts, collision, warps, and the level command script
  itself are not extracted.
- Models are limited to `model_ids.h`; per-level geometry models defined
  elsewhere are not included.
