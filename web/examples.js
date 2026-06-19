// Curated example queries. Each shows off a different corner of the schema and
// doubles as a tutorial for what is in the database. Clicking one loads it into
// the editor and runs it.
window.SM64_EXAMPLES = [
  {
    title: "Most-placed behaviors",
    sql: `-- Which object behaviors appear most across every level?
SELECT behavior, COUNT(*) AS placements
FROM object
GROUP BY behavior
ORDER BY placements DESC
LIMIT 15;`,
  },
  {
    title: "Object spawn graph",
    sql: `-- A placed object's behavior, and what that behavior spawns at runtime.
-- (behavior_spawn is a VIEW over the behavior bytecode.)
SELECT o.level, o.behavior AS placed, s.spawned_behavior AS spawns, s.spawned_model
FROM object o
JOIN behavior_spawn s ON o.behavior = s.behavior_name
WHERE s.spawned_behavior IS NOT NULL
GROUP BY o.behavior, s.spawned_behavior
ORDER BY o.level;`,
  },
  {
    title: "Ghost behaviors (spawned, never placed)",
    sql: `-- Behaviors that only exist as runtime children: they are spawned by a
-- parent but never placed directly in any level file.
SELECT DISTINCT s.spawned_behavior AS child_only
FROM behavior_spawn s
WHERE s.spawned_behavior IS NOT NULL
  AND s.spawned_behavior NOT IN (SELECT behavior FROM object)
  AND s.spawned_behavior NOT IN (SELECT behavior FROM macro_preset)
  AND s.spawned_behavior NOT IN (SELECT behavior FROM special_preset)
ORDER BY child_only;`,
  },
  {
    title: "Shared engine helpers",
    sql: `-- Native C functions called by the most behaviors -- the engine's
-- shared building blocks. (behavior_native is a VIEW over CALL_NATIVE.)
SELECT func, COUNT(DISTINCT behavior_name) AS used_by
FROM behavior_native
GROUP BY func
ORDER BY used_by DESC
LIMIT 12;`,
  },
  {
    title: "Animation reuse leaderboard",
    sql: `-- Which animation sets are shared by more than one actor?
SELECT symbol AS animation_set,
       COUNT(*) AS used_by,
       group_concat(behavior_name, ', ') AS behaviors
FROM behavior_resource
WHERE kind = 'animation'
GROUP BY symbol
HAVING used_by > 1
ORDER BY used_by DESC;`,
  },
  {
    title: "What spawns a coin?",
    sql: `-- Find every behavior that spawns a coin, by behavior or by model.
SELECT behavior_name AS spawner, spawned_behavior, spawned_model
FROM behavior_spawn
WHERE spawned_behavior LIKE '%Coin%'
   OR spawned_model LIKE '%COIN%';`,
  },
  {
    title: "Behavior bytecode (Goomba)",
    sql: `-- The full bytecode script for one behavior, in order.
SELECT seq, command, args
FROM behavior_command
WHERE behavior_name = 'bhvGoomba'
ORDER BY seq;`,
  },
  {
    title: "Opcode histogram",
    sql: `-- The shape of the behavior virtual machine: how often each opcode appears.
SELECT command, COUNT(*) AS n
FROM behavior_command
GROUP BY command
ORDER BY n DESC;`,
  },
  {
    title: "Pure-script behaviors (no C code)",
    sql: `-- Behaviors whose logic is entirely bytecode -- they never CALL_NATIVE.
SELECT b.behavior_name
FROM behavior b
LEFT JOIN behavior_native n ON b.behavior_name = n.behavior_name
WHERE n.behavior_name IS NULL
  AND b.behavior_name IN (SELECT behavior_name FROM behavior_command)
ORDER BY b.behavior_name;`,
  },
  {
    title: "Where is MODEL_YELLOW_COIN used?",
    sql: `-- The "open door": json_each finds a symbol in ANY argument slot of ANY
-- command, regardless of opcode or position.
SELECT behavior_name, command, args
FROM behavior_command, json_each(args_json)
WHERE json_each.value = 'MODEL_YELLOW_COIN';`,
  },
  {
    title: "Busiest levels",
    sql: `-- Total placed things per level, across the three placement tables.
SELECT level, SUM(n) AS things FROM (
  SELECT level, COUNT(*) AS n FROM object        GROUP BY level
  UNION ALL
  SELECT level, COUNT(*) AS n FROM macro_object  GROUP BY level
  UNION ALL
  SELECT level, COUNT(*) AS n FROM special_object GROUP BY level
)
GROUP BY level
ORDER BY things DESC
LIMIT 15;`,
  },
  {
    title: "Dialog text",
    sql: `-- Read the game's dialog lines straight out of the database.
SELECT dialog_name, text
FROM dialog
LIMIT 20;`,
  },
];
