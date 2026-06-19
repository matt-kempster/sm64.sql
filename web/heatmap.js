"use strict";

// ---------------------------------------------------------------------------
// Heatmap tab: a nested cross-tab of objects against levels/courses. Rows are
// the game's object lists (behavior.obj_list); expanding one reveals its
// behaviors. Each cell is shaded by placement count -- a JOIN + GROUP BY made
// visible. Clicking any cell/label opens the underlying query in the Query tab.
// Wrapped in an IIFE so its names stay local (app.js owns the global `db`).
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;

  const expanded = new Set(); // object-list categories currently expanded
  let lastCats = []; // category names from the most recent render

  const strip = (s) => String(s).replace(/^bhv/, "").replace(/^COURSE_/, "");
  const catName = (c) =>
    c === "(none)" ? "(none)" : c.replace(/^OBJ_LIST_/, "").toLowerCase();

  function load(dim) {
    const sql =
      dim === "course"
        ? `SELECT o.behavior, COALESCE(NULLIF(b.obj_list,''),'(none)') cat,
                  l.course_name k, COUNT(*) c
           FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name
           JOIN level l ON o.level = l.folder
           GROUP BY o.behavior, cat, k`
        : `SELECT o.behavior, COALESCE(NULLIF(b.obj_list,''),'(none)') cat,
                  o.level k, COUNT(*) c
           FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name
           GROUP BY o.behavior, cat, k`;
    const r = sdb().exec(sql);
    return r.length ? r[0].values : [];
  }

  // Roll the flat (behavior, cat, col, count) rows up into categories -> behaviors.
  function build(rows) {
    const cats = new Map();
    const colTotals = new Map();
    rows.forEach(([beh, cat, k, c]) => {
      if (k == null) return;
      if (!cats.has(cat)) cats.set(cat, { total: 0, byCol: new Map(), behs: new Map() });
      const C = cats.get(cat);
      C.total += c;
      C.byCol.set(k, (C.byCol.get(k) || 0) + c);
      if (!C.behs.has(beh)) C.behs.set(beh, { total: 0, byCol: new Map() });
      const B = C.behs.get(beh);
      B.total += c;
      B.byCol.set(k, (B.byCol.get(k) || 0) + c);
      colTotals.set(k, (colTotals.get(k) || 0) + c);
    });
    const cols = [...colTotals.keys()].sort(
      (a, b) => colTotals.get(b) - colTotals.get(a) || a.localeCompare(b)
    );
    const catList = [...cats.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.total - a.total);
    catList.forEach((c) => {
      c.behList = [...c.behs.entries()]
        .map(([name, v]) => ({ name, ...v }))
        .sort((a, b) => b.total - a.total);
    });
    // Separate color scales: category subtotals dwarf single behaviors, so
    // coloring both on one scale would wash the behavior rows out.
    let catMax = 0;
    let behMax = 0;
    catList.forEach((c) =>
      cols.forEach((k) => {
        const v = c.byCol.get(k) || 0;
        if (v > catMax) catMax = v;
        c.behList.forEach((b) => {
          const bv = b.byCol.get(k) || 0;
          if (bv > behMax) behMax = bv;
        });
      })
    );
    return { cols, catList, catMax, behMax };
  }

  function heat(c, max) {
    if (!c) return { bg: "", fg: "" };
    const t = Math.sqrt(c) / Math.sqrt(max || 1);
    const a = 0.12 + 0.88 * t;
    return { bg: `rgba(228,0,15,${a.toFixed(3)})`, fg: a > 0.55 ? "#fff" : "#5a1216" };
  }

  // --- queries handed to the Query tab ---
  const catCond = (cat) =>
    cat === "(none)" ? "(b.obj_list IS NULL OR b.obj_list = '')" : `b.obj_list = '${cat}'`;

  function catRowQuery(cat, dim) {
    const join = dim === "course" ? "JOIN level l ON o.level = l.folder" : "";
    const col = dim === "course" ? "l.course_name" : "o.level";
    return `-- ${catName(cat)} objects across ${dim}s
SELECT ${col} AS ${dim}, COUNT(*) AS n
FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name ${join}
WHERE ${catCond(cat)}
GROUP BY ${col} ORDER BY n DESC;`;
  }

  function catCellQuery(cat, dim, k) {
    const join = dim === "course" ? "JOIN level l ON o.level = l.folder" : "";
    const colCond = dim === "course" ? `l.course_name = '${k}'` : `o.level = '${k}'`;
    return `-- ${catName(cat)} objects in ${strip(k)}
SELECT o.behavior, COUNT(*) AS n
FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name ${join}
WHERE ${catCond(cat)} AND ${colCond}
GROUP BY o.behavior ORDER BY n DESC;`;
  }

  function behRowQuery(beh) {
    return `-- where ${strip(beh)} is placed
SELECT level, COUNT(*) AS placements
FROM object WHERE behavior = '${beh}'
GROUP BY level ORDER BY placements DESC;`;
  }

  function behCellQuery(beh, dim, k) {
    if (dim === "course") {
      return `-- ${strip(beh)} placed in ${strip(k)}
SELECT o.level, o.initial_x AS x, o.initial_y AS y, o.initial_z AS z,
       o.model_name, o.bhv_param
FROM object o JOIN level l ON o.level = l.folder
WHERE o.behavior = '${beh}' AND l.course_name = '${k}'
ORDER BY o.level;`;
    }
    return `-- ${strip(beh)} placed in ${k}
SELECT level, initial_x AS x, initial_y AS y, initial_z AS z,
       model_name, bhv_param
FROM object
WHERE behavior = '${beh}' AND level = '${k}'
ORDER BY level;`;
  }

  function makeCell(value, max, title, onClick) {
    const td = document.createElement("td");
    if (value) {
      const { bg, fg } = heat(value, max);
      td.style.background = bg;
      td.style.color = fg;
      td.textContent = value;
      td.title = title;
      td.addEventListener("click", onClick);
    }
    return td;
  }

  function render() {
    const dim = el("heat-cols").value;
    const { cols, catList, catMax, behMax } = build(load(dim));
    lastCats = catList.map((c) => c.name);

    el("heat-status").textContent = `${catList.length} object lists · ${cols.length} ${dim}s`;
    const allOpen = lastCats.length > 0 && lastCats.every((n) => expanded.has(n));
    el("heat-expand").textContent = allOpen ? "Collapse all" : "Expand all";

    const table = document.createElement("table");
    table.className = "heatmap";

    const thead = document.createElement("thead");
    const htr = document.createElement("tr");
    const corner = document.createElement("th");
    corner.className = "corner";
    corner.innerHTML = `<span class="corner-label">object list ╲ ${dim}</span>`;
    htr.appendChild(corner);
    cols.forEach((k) => {
      const th = document.createElement("th");
      th.className = "colhead";
      th.title = k;
      th.innerHTML = `<span class="rot">${strip(k)}</span>`;
      htr.appendChild(th);
    });
    thead.appendChild(htr);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    catList.forEach((cat) => {
      const isOpen = expanded.has(cat.name);

      const tr = document.createElement("tr");
      tr.className = "cat-row";
      const rh = document.createElement("th");
      rh.className = "rowhead cat";
      rh.innerHTML =
        `<span class="twirl">${isOpen ? "▾" : "▸"}</span>` +
        `${catName(cat.name)} <span class="muted">${cat.total}</span>`;
      rh.title = `${cat.name} — click to ${isOpen ? "collapse" : "expand"}`;
      rh.addEventListener("click", () => {
        if (isOpen) expanded.delete(cat.name);
        else expanded.add(cat.name);
        render();
      });
      tr.appendChild(rh);
      cols.forEach((k) => {
        const v = cat.byCol.get(k) || 0;
        tr.appendChild(
          makeCell(v, catMax, `${catName(cat.name)} × ${strip(k)} = ${v}`, () =>
            window.sm64CopyQuery(catCellQuery(cat.name, dim, k))
          )
        );
      });
      tbody.appendChild(tr);

      if (isOpen) {
        cat.behList.forEach((b) => {
          const btr = document.createElement("tr");
          btr.className = "beh-row";
          const bh = document.createElement("th");
          bh.className = "rowhead beh";
          bh.textContent = strip(b.name);
          bh.title = `${b.name} — ${b.total} placed; click for the breakdown`;
          bh.addEventListener("click", () => window.sm64CopyQuery(behRowQuery(b.name)));
          btr.appendChild(bh);
          cols.forEach((k) => {
            const v = b.byCol.get(k) || 0;
            btr.appendChild(
              makeCell(v, behMax, `${strip(b.name)} × ${strip(k)} = ${v}`, () =>
                window.sm64CopyQuery(behCellQuery(b.name, dim, k))
              )
            );
          });
          tbody.appendChild(btr);
        });
      }
    });
    table.appendChild(tbody);

    const scroll = el("heat-scroll");
    scroll.innerHTML = "";
    scroll.appendChild(table);
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    el("heat-cols").addEventListener("change", render);
    el("heat-expand").addEventListener("click", () => {
      const allOpen = lastCats.length > 0 && lastCats.every((n) => expanded.has(n));
      if (allOpen) expanded.clear();
      else lastCats.forEach((n) => expanded.add(n));
      render();
    });
  }

  window.SM64Heatmap = {
    onShow() {
      ensureInit();
      render();
    },
  };
})();
