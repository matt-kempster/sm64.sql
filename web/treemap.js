"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: the whole game's object population as nested rectangles. Each
// level is a block sized by its object count; inside, each tile is a behavior
// sized by count and colored by its object list (object JOIN behavior). Layout
// is D3's squarified treemap. Wrapped in an IIFE; app.js owns the global `db`.
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;

  const strip = (s) => String(s).replace(/^bhv/, "");
  const catLabel = (c) => (c ? c.replace(/^OBJ_LIST_/, "").toLowerCase() : "(none)");

  // Stable color per object list. "" (no behavior match) gets a neutral gray.
  const color = d3
    .scaleOrdinal()
    .unknown("#b3ab97")
    .domain([
      "OBJ_LIST_SURFACE",
      "OBJ_LIST_DEFAULT",
      "OBJ_LIST_LEVEL",
      "OBJ_LIST_GENACTOR",
      "OBJ_LIST_POLELIKE",
      "OBJ_LIST_SPAWNER",
      "OBJ_LIST_PUSHABLE",
      "OBJ_LIST_DESTRUCTIVE",
      "OBJ_LIST_UNIMPORTANT",
      "OBJ_LIST_PLAYER",
    ])
    .range(d3.schemeTableau10);

  function loadLevels() {
    const r = sdb().exec(
      `SELECT o.level, o.behavior, b.obj_list, COUNT(*) c
       FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name
       GROUP BY o.level, o.behavior`
    );
    const rows = r.length ? r[0].values : [];
    const byLevel = new Map();
    rows.forEach(([level, beh, olist, c]) => {
      if (!byLevel.has(level)) byLevel.set(level, []);
      byLevel.get(level).push({ name: beh, obj_list: olist || "", value: c });
    });
    return Array.from(byLevel, ([name, children]) => ({ name, children }));
  }

  function leafQuery(level, beh) {
    return `-- ${strip(beh)} placed in ${level}
SELECT level, initial_x AS x, initial_y AS y, initial_z AS z,
       model_name, behavior, bhv_param
FROM object
WHERE level = '${level}' AND behavior = '${beh}'
ORDER BY level;`;
  }

  function buildLegend(cats) {
    const legend = el("tm-legend");
    legend.innerHTML = "";
    cats.forEach((c) => {
      const item = document.createElement("span");
      item.className = "legend-item static";
      item.innerHTML =
        `<span class="swatch" style="background:${color(c)}"></span>${catLabel(c)}`;
      legend.appendChild(item);
    });
  }

  function render() {
    const stage = el("tm-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const svg = el("tm-svg");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (W < 2 || H < 2) return;

    const levels = loadLevels();
    const root = d3
      .hierarchy({ name: "root", children: levels })
      .sum((d) => d.value || 0)
      .sort((a, b) => b.value - a.value);

    d3
      .treemap()
      .size([W, H])
      .paddingInner(1)
      .paddingTop(15)
      .paddingOuter(2)
      .round(true)(root);

    const present = Array.from(new Set(root.leaves().map((d) => d.data.obj_list))).sort();
    buildLegend(present);
    el("tm-status").textContent =
      `${levels.length} levels · ${root.leaves().length} object types · ${root.value} placements`;

    const tip = el("tm-tooltip");
    const sel = d3.select(svg);

    // Level blocks (depth 1): border + name label in the reserved top strip.
    const lvl = sel
      .selectAll("g.tm-lvl")
      .data(root.children || [])
      .join("g")
      .attr("class", "tm-lvl");
    lvl
      .append("rect")
      .attr("x", (d) => d.x0)
      .attr("y", (d) => d.y0)
      .attr("width", (d) => d.x1 - d.x0)
      .attr("height", (d) => d.y1 - d.y0)
      .attr("class", "tm-lvl-box");
    lvl
      .filter((d) => d.x1 - d.x0 > 34)
      .append("text")
      .attr("class", "tm-lvl-label")
      .attr("x", (d) => d.x0 + 4)
      .attr("y", (d) => d.y0 + 11)
      .text((d) => d.data.name);

    // Behavior tiles (leaves).
    const leaf = sel
      .selectAll("g.tm-cell")
      .data(root.leaves())
      .join("g")
      .attr("class", "tm-cell")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`);

    leaf
      .append("rect")
      .attr("width", (d) => d.x1 - d.x0)
      .attr("height", (d) => d.y1 - d.y0)
      .attr("fill", (d) => color(d.data.obj_list))
      .attr("stroke", "#fff")
      .on("mousemove", (event, d) => {
        tip.innerHTML =
          `<strong>${strip(d.data.name)}</strong> × ${d.value}<br>` +
          `<span class="muted">${d.parent.data.name} · ${catLabel(d.data.obj_list)}</span>`;
        tip.style.display = "block";
        const r = stage.getBoundingClientRect();
        tip.style.left = event.clientX - r.left + 12 + "px";
        tip.style.top = event.clientY - r.top + 12 + "px";
      })
      .on("mouseleave", () => (tip.style.display = "none"))
      .on("click", (event, d) =>
        window.sm64RunInQuery(leafQuery(d.parent.data.name, d.data.name))
      );

    // Label tiles big enough to hold text.
    leaf
      .filter((d) => d.x1 - d.x0 > 42 && d.y1 - d.y0 > 16)
      .append("text")
      .attr("class", "tm-cell-label")
      .attr("x", 3)
      .attr("y", 12)
      .text((d) => strip(d.data.name));
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-treemap").classList.contains("active")) render();
      }, 150);
    });
  }

  window.SM64Treemap = {
    onShow() {
      ensureInit();
      render();
    },
  };
})();
