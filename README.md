# sm64.sql

Load [Super Mario 64 decompilation](https://github.com/n64decomp/sm64) game
data into a SQLite database so you can explore it with SQL.

The decomp stores its data as C macros and tables (`OBJECT(...)`,
`MACRO_OBJECT(...)`, `enum MacroPresets`, `#define MODEL_*`, ...). `sm64.sql`
reads those source files and writes the equivalent rows into a SQLite database,
so questions like "which objects appear only in act 1?", "what music plays in
each course?", or "where does each painting warp to?" become one-line queries.

It currently populates 22 tables (plus 10 derived views) spanning placed
objects, models and per-level model loads, behaviors and their command scripts
and native C code, levels/courses/areas, warps, dialog, music, animations,
sounds, the in-game course and star names, and the named constants behavior
params use — see the
[schema](#schema) and [example queries](#example-queries) below.

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

## Web playground

[`web/`](web/) is a static, zero-backend site that loads the database into your
browser with [sql.js](https://sql.js.org) and lets you run your own SQL (with
syntax highlighting and schema-aware autocomplete), browse the schema, try
curated example queries, and explore visual tabs — a map of any
level's placed objects, an object × level/course heatmap, and a treemap of the
game's object population (the last two built on [D3](https://d3js.org)). Every
chart cell links back to the JOIN behind it. It's all client-side, so nothing
you type leaves the page. Build the database and serve the folder:

```sh
sm64-sql -r /path/to/sm64 -d web/sm64.db -o
cd web && python3 -m http.server 8000   # then open http://localhost:8000
```

A GitHub Actions workflow rebuilds the database and deploys the site to GitHub
Pages on every push to `master`. See [`web/README.md`](web/README.md).

## Schema

| Table | Source | Columns |
| --- | --- | --- |
| `object` | `levels/*/script.c` | `model_name`, `level`, `initial_x/y/z`, `initial_rot_x/y/z`, `bhv_param`, `bhv_param_value`, `bhv_param_1` … `bhv_param_4`, `behavior`, `in_act_1` … `in_act_6` |
| `macro_object` | `levels/**/macro.inc.c` | `macro_name`, `level`, `yaw`, `pos_x/y/z`, `bhv_param`, `bhv_param_value` |
| `model` | `include/model_ids.h` | `model_name`, `model_id` |
| `model_load` | `levels/*/script.c` + `levels/scripts.c` | `level` (`common` = shared), `model_name`, `geo`, `layer`, `kind` (`geo`/`dl`) |
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
| `behavior_command` | `data/behavior_data.c` | `behavior_name`, `seq`, `command`, `args`, `args_json` |
| `behavior_call` | `src/game/behaviors/*.inc.c` | `behavior_name`, `function`, `seq`, `call`, `args`, `args_json`, `file`, `line` |
| `warp` | `levels/*/script.c` | `level`, `area` (0 = level-global), `node_id`, `dest_level`, `dest_area`, `dest_node`, `flags`, `is_painting` |
| `instant_warp` | `levels/*/script.c` | `level`, `area`, `warp_index`, `dest_area`, `displace_x/y/z` |
| `area` | `levels/*/script.c` | `level`, `area`, `geo`, `terrain_type`, `background_music`, `dialog` |
| `mario_animation` | `include/mario_animation_ids.h` | `anim_name`, `anim_id` |
| `sound` | `include/sounds.h` | `sound_name`, `sound_id`, `bank` |
| `constant` | `include/object_constants.h` + `src/game/level_update.h` | `name`, `value`, `source` (`warp_nodes`/`object_constants`) |

Names such as `MODEL_BOO`, `bhvGoomba`, and `macro_yellow_coin_2` are kept as
the symbolic strings used in the source, so the tables join naturally on those
names.

### Behavior scripts

Each behavior is a little bytecode program — an ordered array of command macros
(`BEGIN`, `CALL_NATIVE`, `SPAWN_CHILD`, `BEGIN_LOOP`, …). The `behavior_command`
table records one row per command, in order (`seq`), keeping the comma-joined
`args` text plus `args_json`, a JSON array of the top-level-split arguments (so
an expression like `(OBJ_FLAG_A | OBJ_FLAG_B)` stays one argument).

Three **views** read that backbone to expose the high-value relations as plain
columns that join like any other table:

| View | From | Columns |
| --- | --- | --- |
| `behavior_spawn` | `SPAWN_CHILD` / `SPAWN_OBJ` / `SPAWN_CHILD_WITH_PARAM` | `behavior_name`, `seq`, `kind`, `spawned_model`, `spawned_behavior`, `bhv_param` |
| `behavior_native` | `CALL_NATIVE` | `behavior_name`, `seq`, `func` (the C function the behavior runs) |
| `behavior_resource` | `LOAD_ANIMATIONS` / `LOAD_COLLISION_DATA` / `SET_MODEL` | `behavior_name`, `seq`, `kind`, `symbol` |

Because the arguments are stored as JSON, `json_each` answers the questions the
views do not — e.g. "which commands name this symbol in *any* argument slot?"

### Behavior native code

A behavior script mostly just `CALL_NATIVE`s into C functions under
`src/game/behaviors/`. The real logic — what an object spawns, the sounds it
plays, the dialog it shows — lives in those functions and the helpers they call,
and the script never names it. The `behavior_call` table is the backbone for
that layer: one row per call site in the C, attributed to the behavior(s) that
reach it. The C is parsed with [tree-sitter](https://tree-sitter.github.io/)
(a real syntax tree, not regex), so every function and every call is enumerated
structurally; each call is attributed by following the static call graph from a
behavior's `CALL_NATIVE` roots through the object code, treating engine helpers
(`spawn_object`, `cur_obj_play_sound_2`, …) as the leaf relation vocabulary.

The same backbone-plus-views pattern then exposes the relations as plain
columns. The target symbol is matched by argument *pattern* (a spawned behavior
is the `bhv*` argument, a model the `MODEL_*` one), so the views are robust to
each helper's differing argument order:

| View | From calls | Columns (besides `behavior_name`, `function`, `file`, `line`, `call`) |
| --- | --- | --- |
| `behavior_calls_spawn` | `spawn_object`, `spawn_object_relative`, … | `spawned_behavior`, `spawned_model` |
| `behavior_calls_sound` | `cur_obj_play_sound_1/2`, `play_sound`, … | `sound` |
| `behavior_calls_model` | `cur_obj_set_model` | `model` |
| `behavior_calls_dialog` | `cur_obj_update_dialog_with_cutscene`, `cutscene_object_with_dialog`, … | `dialog` |
| `behavior_calls_morph` | `cur_obj_set_behavior`, `obj_set_behavior` | `becomes_behavior` |
| `behavior_calls_seek` | `cur_obj_nearest_object_with_behavior`, `cur_obj_has_behavior`, … | `target_behavior` |

Each view lists only the call sites whose target *resolves to a literal symbol*,
so the target column is never null. A call that passes its target as a runtime
value — a signpost reading its dialog id from `oBhvParams2ndByte`, a spawn of a
behavior held in a variable — stays in `behavior_call` (query it directly) but is
not surfaced as a clean edge here.

Completeness is auditable rather than assumed: nothing is filtered at parse time,
so `behavior_call_unclassified` lists every captured call a relation view does
*not* classify (most-frequent first) — the visible residue to scan for a helper
family worth promoting to a relation.

This is what makes runtime spawns visible that the script alone cannot show: a
Bob-omb's explosion (`spawn_object(bhvExplosion)` inside `bobomb_act_explode`)
has no `SPAWN_*` opcode, so it is absent from `behavior_spawn` but present in
`behavior_calls_spawn`.

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

Those symbolic byte values (`WARP_NODE_0A`, `STAR_INDEX_ACT_3`,
`GOOMBA_SIZE_HUGE`) are names; the `constant` table resolves each to its integer
value, so you can join a param byte to its number.

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

-- One model slot is reused per level: what geo is MODEL_LEVEL_GEOMETRY_03 in each?
SELECT level, geo FROM model_load
WHERE model_name = 'MODEL_LEVEL_GEOMETRY_03' AND level <> 'common'
ORDER BY level;

-- Resolve a symbolic param byte to its number via the constant table.
SELECT o.level, o.behavior, o.bhv_param_2 AS warp_node, c.value
FROM object o JOIN constant c ON o.bhv_param_2 = c.name
WHERE o.bhv_param_2 LIKE 'WARP_NODE_%';

-- The object spawn graph: which behavior spawns which (a self-join).
SELECT behavior_name AS parent, spawned_behavior AS child, spawned_model
FROM behavior_spawn
WHERE spawned_behavior IS NOT NULL
ORDER BY parent;

-- What C code implements each behavior? (its init/loop/update functions)
SELECT behavior_name, group_concat(func, ', ') AS funcs
FROM behavior_native GROUP BY behavior_name;

-- Which behaviors load a given collision mesh / animation set?
SELECT behavior_name, symbol FROM behavior_resource WHERE kind = 'collision';

-- The *full* spawn graph, including runtime spawns that live only in C and have
-- no SPAWN_* opcode (e.g. a Bob-omb's explosion). Compare to behavior_spawn.
SELECT behavior_name AS parent, spawned_behavior AS child, function, file, line
FROM behavior_calls_spawn
WHERE spawned_behavior IS NOT NULL ORDER BY parent;

-- Which objects make a given sound, and from which C function?
SELECT behavior_name, function, sound FROM behavior_calls_sound
WHERE sound = 'SOUND_OBJ_BOBOMB_WALK';

-- Completeness audit: captured C calls that no relation view classifies yet.
SELECT call, n FROM behavior_call_unclassified LIMIT 25;

-- Read a single behavior's command script, in order.
SELECT seq, command, args FROM behavior_command
WHERE behavior_name = 'bhvGoomba' ORDER BY seq;

-- The open door: every command that names a symbol in ANY argument slot.
SELECT behavior_name, command FROM behavior_command, json_each(args_json)
WHERE json_each.value = 'MODEL_BOWSER_FLAME';
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

22 tables (plus 10 views) are populated from a full current `n64decomp/sm64`
checkout: placed objects, macro objects and special objects; models and
per-level model loads, behaviors and their command scripts and native C code,
macro/special presets; levels, courses and areas; warps and instant warps;
dialog text, music sequences, Mario animations, and sound effects; the in-game
course and star names; and the named constants behavior params use. Counts are
cross-checked against the source.

Behavior parameters (`bhvParam` / preset `param`) are captured on the object,
macro object, special object, and macro preset tables — split into their
`BPARAM` byte slots and resolved to a number when the expression is numeric. The
symbolic byte values (`WARP_NODE_*`, `STAR_INDEX_*`, `GOOMBA_SIZE_*`, …) resolve
to integers via the `constant` table.

Behavior command scripts are recorded as an ordered command stream
(`behavior_command`), but their *control flow* is not resolved: `GOTO` / `CALL`
jump targets are kept as the raw argument text rather than linked to a command
position. The data-binding opcodes (spawns, native calls, loaded resources) are
surfaced as views; the loop/jump opcodes are just rows.

Not yet captured (contributions welcome):
- Geo layouts, collision geometry, trajectories, and the *level* command script
  flow (the `JUMP`/`CALL`/`LOOP` in `levels/scripts.c`) are not extracted — see
  the geometry note in the project brief; these are intentionally out of scope.
- The `geo` symbols in `model_load` are recorded as names; the geo layouts they
  point at are not parsed (out of scope, as above).
- A few values are kept verbatim rather than resolved: e.g. an area whose music
  is `SEQ_x | SEQ_VARIATION` won't join to `sequence` by name.
