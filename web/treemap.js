"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: a zoomable, single-tier treemap of the game's object population,
// drilling level → object list → behavior. Only the children of the current
// focus are shown, all styled identically and sized by placement count. Click a
// tile to zoom into it; the breadcrumb zooms back out; clicking a behavior (a
// leaf) copies its query. Wrapped in an IIFE; app.js owns the global `db`.
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;
  let root = null; // full hierarchy
  let focus = null; // node currently filling the view

  const strip = (s) => String(s).replace(/^bhv/, "");
  const catLabel = (c) => (c ? c.replace(/^OBJ_LIST_/, "").toLowerCase() : "(none)");
  const escapeHtml = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

  // One cheerful palette, used at every tier so the tiles look uniform.
  const PALETTE = [
    "#ff8787", "#ffa94d", "#ffd43b", "#a9e34b", "#69db7c", "#38d9a9",
    "#3bc9db", "#4dabf7", "#748ffc", "#9775fa", "#da77f2", "#f783ac",
  ];
  const colorByName = d3.scaleOrdinal(PALETTE);

  const layout = d3.treemap().paddingInner(3).round(true);

  // Readable text color for a given tile fill.
  function textOn(bg) {
    const c = d3.color(bg).rgb();
    const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
    return lum > 0.62 ? "#1d2330" : "#ffffff";
  }

  // Display name per tier: levels/behaviors as-is (minus bhv), lists prettified.
  function displayName(n) {
    if (n.depth === 0) return "all levels";
    if (n.depth === 2) return catLabel(n.data.name);
    return strip(n.data.name);
  }

  // level → object list → behaviors (leaves)
  function loadTree() {
    const r = sdb().exec(
      `SELECT o.level, o.behavior, COALESCE(b.obj_list, '') AS olist, COUNT(*) c
       FROM object o LEFT JOIN behavior b ON o.behavior = b.behavior_name
       GROUP BY o.level, o.behavior`
    );
    const rows = r.length ? r[0].values : [];
    const levels = new Map();
    rows.forEach(([level, beh, olist, c]) => {
      if (!levels.has(level)) levels.set(level, new Map());
      const cats = levels.get(level);
      if (!cats.has(olist)) cats.set(olist, []);
      cats.get(olist).push({ name: beh, value: c });
    });
    return Array.from(levels, ([name, cats]) => ({
      name,
      children: Array.from(cats, ([cname, behs]) => ({ name: cname, children: behs })),
    }));
  }

  function leafQuery(level, beh) {
    return `-- ${strip(beh)} placed in ${level}
SELECT level, initial_x AS x, initial_y AS y, initial_z AS z,
       model_name, behavior, bhv_param
FROM object
WHERE level = '${level}' AND behavior = '${beh}'
ORDER BY level;`;
  }

  function zoomTo(node) {
    focus = node;
    draw();
  }

  function buildBreadcrumb() {
    const bc = el("tm-breadcrumb");
    bc.innerHTML = "";
    focus.ancestors().reverse().forEach((n, i) => {
      if (i) {
        const sep = document.createElement("span");
        sep.className = "tm-sep";
        sep.textContent = "▸";
        bc.appendChild(sep);
      }
      const crumb = document.createElement("button");
      crumb.className = "tm-crumb" + (n === focus ? " current" : "");
      crumb.textContent = displayName(n);
      if (n !== focus) crumb.addEventListener("click", () => zoomTo(n));
      bc.appendChild(crumb);
    });
  }

  function draw() {
    const stage = el("tm-stage");
    const W = stage.clientWidth;
    const H = stage.clientHeight;
    const svg = el("tm-svg");
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (W < 2 || H < 2) return;

    layout.size([W, H])(focus); // lay the focus subtree out to fill the view
    const tiles = focus.children || [];

    buildBreadcrumb();
    const kind = focus.depth === 0 ? "levels" : focus.depth === 1 ? "object lists" : "behaviors";
    el("tm-status").textContent = `${tiles.length} ${kind} · ${focus.value} placements`;

    const tip = el("tm-tooltip");
    const layer = d3.select(svg).append("g").attr("class", "tm-layer");

    const g = layer
      .selectAll("g.tm-tile")
      .data(tiles)
      .enter()
      .append("g")
      .attr("class", "tm-tile")
      .attr("transform", (d) => `translate(${d.x0},${d.y0})`)
      .on("mousemove", (event, d) => {
        const path = d
          .ancestors()
          .slice(1, -1)
          .reverse()
          .map(displayName)
          .join(" · ");
        tip.innerHTML =
          `<strong>${escapeHtml(displayName(d))}</strong> × ${d.value}` +
          (path ? `<br><span class="muted">${escapeHtml(path)}</span>` : "") +
          (d.children ? `<br><span class="muted">click to zoom in</span>` : "");
        tip.style.display = "block";
        const r = stage.getBoundingClientRect();
        tip.style.left = event.clientX - r.left + 12 + "px";
        tip.style.top = event.clientY - r.top + 12 + "px";
      })
      .on("mouseleave", () => (tip.style.display = "none"))
      .on("click", (event, d) => {
        if (d.children) zoomTo(d);
        else {
          const level = d.ancestors().find((a) => a.depth === 1);
          window.sm64CopyQuery(leafQuery(level.data.name, d.data.name));
        }
      });

    g.append("rect")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .attr("rx", 4)
      .attr("ry", 4)
      .attr("fill", (d) => colorByName(d.data.name));

    // Labels via foreignObject so CSS handles truncation/ellipsis consistently.
    g.append("foreignObject")
      .attr("class", "tm-fo")
      .attr("width", (d) => Math.max(0, d.x1 - d.x0))
      .attr("height", (d) => Math.max(0, d.y1 - d.y0))
      .html((d) => {
        const w = d.x1 - d.x0;
        const h = d.y1 - d.y0;
        if (w < 26 || h < 16) return "";
        const fg = textOn(colorByName(d.data.name));
        return (
          `<div class="tm-label" style="color:${fg}">` +
          `<span class="tm-name">${escapeHtml(displayName(d))}</span>` +
          `<span class="tm-val">${d.value}${d.children ? " ▸" : ""}</span>` +
          `</div>`
        );
      });
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-treemap").classList.contains("active")) draw();
      }, 150);
    });
  }

  window.SM64Treemap = {
    onShow() {
      ensureInit();
      root = d3
        .hierarchy({ name: "root", children: loadTree() })
        .sum((d) => d.value || 0)
        .sort((a, b) => b.value - a.value);
      focus = root;
      draw();
    },
  };
})();
