# sm64.sql

Load [Super Mario 64 decompilation](https://github.com/n64decomp/sm64) game
data into a SQLite database so you can explore it with SQL.

The decomp stores its data as C macros and tables (`OBJECT(...)`,
`MACRO_OBJECT(...)`, `enum MacroPresets`, `#define MODEL_*`, ...). `sm64.sql`
reads those source files and writes the equivalent rows into a SQLite database,
so questions like "which objects appear only in act 1?", "what music plays in
each course?", or "where does each painting warp to?" become one-line queries.

It currently populates 18 tables spanning placed objects, models, behaviors,
levels/courses/areas, warps, dialog, music, animations, sounds, and the in-game
course and star names — see the [schema](#schema) and
[example queries](#example-queries) below.

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
| `object` | `levels/*/script.c` | `model_name`, `level`, `initial_x/y/z`, `initial_rot_x/y/z`, `bhv_param`, `bhv_param_value`, `bhv_param_1` … `bhv_param_4`, `behavior`, `in_act_1` … `in_act_6` |
| `macro_object` | `levels/**/macro.inc.c` | `macro_name`, `level`, `yaw`, `pos_x/y/z`, `bhv_param`, `bhv_param_value` |
| `model` | `include/model_ids.h` | `model_name`, `model_id` |
| `macro_preset` | `include/macro_presets.h` + `macro_presets.inc.c` | `macro_name`, `behavior`, `model_name`, `param`, `param_value` |
| `level` | `levels/level_defines.h` | `level_name`, `course_name`, `folder`, `internal_name`, `is_stub` |
| `course` | `levels/course_defines.h` | `course_name`, `display_name`, `dance_cutscene`, `is_bonus` |
| `course_name` | `text/us/courses.h` | `course_name`, `number` (1-15, 0 for bonus), `name` (in-game file-select name) |
| `star` | `text/us/courses.h` | `course_name`, `kind` (`main`/`secret`), `act` (1-6, 0 for secret), `name` |
| `sequence` | `include/seq_ids.h` | `seq_name`, `seq_id` (music tracks) |
| `dialog` | `text/us/dialogs.h` + `include/dialog_ids.h` | `dialog_name`, `dialog_id`, `lines_per_box`, `left_offset`, `width`, `text` |
| `special_preset` | `include/special_presets.h` + `special_presets.inc.c` | `preset_name`, `preset_id`, `preset_type`, `default_param`, `model_name`, `behavior` |
| `special_object` | `levels/**/collision.inc.c` | `preset_name`, `preset_id`, `level`, `area`, `pos_x/y/z`, `yaw`, `bhv_param`, `bhv_param_value` |
| `behavior` | `include/behavior_data.h` + `data/behavior_data.c` | `behavior_name`, `obj_list` |
| `warp` | `levels/*/script.c` | `level`, `area` (0 = level-global), `node_id`, `dest_level`, `dest_area`, `dest_node`, `flags`, `is_painting` |
| `instant_warp` | `levels/*/script.c` | `level`, `area`, `warp_index`, `dest_area`, `displace_x/y/z` |
| `area` | `levels/*/script.c` | `level`, `area`, `geo`, `terrain_type`, `background_music`, `dialog` |
| `mario_animation` | `include/mario_animation_ids.h` | `anim_name`, `anim_id` |
| `sound` | `include/sounds.h` | `sound_name`, `sound_id`, `bank` |

Names such as `MODEL_BOO`, `bhvGoomba`, and `macro_yellow_coin_2` are kept as
the symbolic strings used in the source, so the tables join naturally on those
names.

### Behavior parameters

Each placed object carries a *behavior parameter* that the game packs into the
32-bit `oBhvParams` field, written in the source as a combination of the
`BPARAMn` macros (`BPARAM1(x)` is the top byte, `BPARAM2(x)` the next, …). Each
byte is an independent, behavior-specific field — a warp node, a dialog id, a
star index, an enemy size, and so on. The tables expose it three ways:

- `bhv_param` keeps the expression exactly as written (e.g.
  `BPARAM1(0x01) | BPARAM2(WARP_NODE_03)` or `DIALOG_089`).
- `bhv_param_value` is the resolved 32-bit integer, but only when the whole
  expression is numeric; expressions that reference a `#define`d constant are
  left `NULL`.
- on `object`, `bhv_param_1` … `bhv_param_4` hold the argument written in each
  `BPARAMn` slot (`bhv_param_2` is the famous `oBhvParams2ndByte`), so a warp
  node or star index can be selected or joined directly.

## Example queries

```sql
-- How many placed objects are in each level?
SELECT level, COUNT(*) AS n FROM object GROUP BY level ORDER BY n DESC;

-- Objects that only appear during act 1.
SELECT level, behavior, initial_x, initial_y, initial_z
FROM object
WHERE in_act_1 AND NOT (in_act_2 OR in_act_3 OR in_act_4 OR in_act_5 OR in_act_6);

-- Each course's display name and the music that plays in its main area.
SELECT c.display_name, s.seq_name
FROM area a
JOIN level l ON a.level = l.folder
JOIN course c ON l.course_name = c.course_name
JOIN sequence s ON a.background_music = s.seq_name
WHERE a.area = 1;

-- The level-to-level warp graph (ignoring within-level warps).
SELECT w.level AS from_level, dl.folder AS to_level, w.node_id
FROM warp w
JOIN level sl ON w.level = sl.folder
JOIN level dl ON w.dest_level = dl.level_name
WHERE w.dest_level <> sl.level_name;

-- Read the intro dialog shown when entering each area.
SELECT a.level, a.area, d.text
FROM area a JOIN dialog d ON a.dialog = d.dialog_name;

-- Which placed objects run a "surface" behavior?
SELECT o.level, o.behavior
FROM object o JOIN behavior b ON o.behavior = b.behavior_name
WHERE b.obj_list = 'OBJ_LIST_SURFACE';

-- Resolve each macro object to its behavior and model.
SELECT mo.level, mo.macro_name, mp.behavior, mp.model_name
FROM macro_object mo JOIN macro_preset mp ON mo.macro_name = mp.macro_name;

-- Read the message on each signpost: its behavior param is a dialog id.
SELECT mo.level, d.text
FROM macro_object mo JOIN dialog d ON mo.bhv_param = d.dialog_name
WHERE mo.macro_name = 'macro_wooden_signpost';

-- Which warp node does each warp object send Mario to? (BPARAM2 = 2nd byte)
SELECT level, behavior, bhv_param_2 AS warp_node
FROM object
WHERE behavior LIKE '%Warp%' AND bhv_param_2 IS NOT NULL;

-- Map each star to the act that awards it (BPARAM1 = 1st byte).
SELECT level, behavior, bhv_param_1 AS star_index
FROM object
WHERE bhv_param_1 LIKE 'STAR_INDEX_%'
ORDER BY level, bhv_param_1;

-- Every main-course star name, by act.
SELECT c.display_name, s.act, s.name
FROM star s JOIN course c ON s.course_name = c.course_name
WHERE s.kind = 'main'
ORDER BY c.display_name, s.act;

-- The payoff: which object awards each named star (star name <- STAR_INDEX byte).
SELECT l.folder AS level, o.behavior, s.name AS star
FROM object o
JOIN level l ON o.level = l.folder
JOIN star s ON s.course_name = l.course_name
           AND s.act = CAST(replace(o.bhv_param_1, 'STAR_INDEX_ACT_', '') AS INTEGER)
WHERE o.bhv_param_1 LIKE 'STAR_INDEX_ACT_%';
```

## How it works

The decomp's level data is written as C *macro invocations* with symbolic
arguments (`OBJECT(MODEL_BOO, ..., bhvGhostHuntBigBoo)`), not plain C that a
compiler would parse directly — the files are designed to be `#include`d and
macro-expanded. `sm64.sql` reads them line by line and pulls the arguments out
of each known macro call. Argument extraction is bracket-aware
(`src/sm64_sql/parse_utils.py`), so behavior-parameter expressions like
`BPARAM2(41)` or `BPARAM1(0) | BPARAM2(1)` are split, decomposed into their
byte slots, and arithmetically resolved when fully numeric
(`src/sm64_sql/behavior_param.py`).

This deliberately stops at *structure*, not *semantics*: it keeps `MODEL_BOO`
as a string rather than expanding it to a number, and likewise leaves a
behavior param such as `BPARAM2(WARP_NODE_03)` as the symbol `WARP_NODE_03`
rather than resolving the `#define` to a number. See
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

18 tables are populated from a full current `n64decomp/sm64` checkout: placed
objects, macro objects and special objects; models, behaviors, macro/special
presets; levels, courses and areas; warps and instant warps; dialog text, music
sequences, Mario animations, and sound effects; and the in-game course and star
names. Counts are cross-checked against the source.

Behavior parameters (`bhvParam` / preset `param`) are captured on the object,
macro object, special object, and macro preset tables — split into their
`BPARAM` byte slots and resolved to a number when the expression is numeric.

Not yet captured (contributions welcome):

- Symbolic param constants (`WARP_NODE_*`, `STAR_INDEX_*`, `GOOMBA_SIZE_*`, …)
  are kept as strings; resolving them to numbers would mean reading the
  scattered `#define` tables (e.g. `include/object_constants.h`).
- Geo layouts, collision geometry, trajectories, and the level command script
  flow (jumps/loops) are not extracted — see the geometry note in the project
  brief; these are intentionally out of scope.
- Models are limited to `model_ids.h`; per-level geometry models defined
  elsewhere are not included.
- A few values are kept verbatim rather than resolved: e.g. an area whose music
  is `SEQ_x | SEQ_VARIATION` won't join to `sequence` by name.
