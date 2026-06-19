"use strict";

// ---------------------------------------------------------------------------
// Treemap tab: a zoomable, single-tier treemap of the game's object population,
// drilling level → object list → behavior. Only the children of the current
// focus are shown, all styled identically and sized by placement count. Click a
// tile to zoom into it; the breadcrumb zooms back out; clicking a behavior (a
// leaf) copies its query. Wrapped in an IIFE; app.js owns the global `db`.
//
// Navigation is a `path` of plain DATA nodes; each draw builds a FRESH d3
// hierarchy rooted at the focused data (depth 0). d3.treemap indexes its
// padding by absolute node.depth, so it must be handed a depth-0 root --
// passing a sub-node yields NaN coordinates and a broken layout.
// ---------------------------------------------------------------------------

(function () {
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();
  let inited = false;
  let treeRootData = null; // { name:'root', children:[levels...] }, built once
  let path = []; // data nodes from root to the current focus

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

  function textOn(bg) {
    const c = d3.color(bg).rgb();
    const lum = (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255;
    return lum > 0.62 ? "#1d2330" : "#ffffff";
  }

  // path[0]=root, [1]=level, [2]=object list. Label each accordingly.
  function crumbLabel(node, i) {
    if (i === 0) return "all levels";
    if (i === 2) return catLabel(node.name);
    return strip(node.name);
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

  function buildBreadcrumb() {
    const bc = el("tm-breadcrumb");
    bc.innerHTML = "";
    path.forEach((node, i) => {
      if (i) {
        const sep = document.createElement("span");
        sep.className = "tm-sep";
        sep.textContent = "▸";
        bc.appendChild(sep);
      }
      const last = i === path.length - 1;
      const crumb = document.createElement("button");
      crumb.className = "tm-crumb" + (last ? " current" : "");
      crumb.textContent = crumbLabel(node, i);
      if (!last) crumb.addEventListener("click", () => { path = path.slice(0, i + 1); draw(); });
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

    // Fresh depth-0 hierarchy rooted at the focused data (see header note).
    const focusData = path[path.length - 1];
    const local = d3
      .hierarchy(focusData)
      .sum((d) => d.value || 0)
      .sort((a, b) => b.value - a.value);
    layout.size([W, H])(local);
    const tiles = local.children || [];

    buildBreadcrumb();
    const kind = path.length === 1 ? "levels" : path.length === 2 ? "object lists" : "behaviors";
    el("tm-status").textContent = `${tiles.length} ${kind} · ${local.value} placements`;

    const tilesAreObjLists = path.length === 2;
    const context = path.slice(1).map((n, i) => crumbLabel(n, i + 1)).join(" · ");
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
        const name = tilesAreObjLists ? catLabel(d.data.name) : strip(d.data.name);
        tip.innerHTML =
          `<strong>${escapeHtml(name)}</strong> × ${d.value}` +
          (context ? `<br><span class="muted">${escapeHtml(context)}</span>` : "") +
          (d.children ? `<br><span class="muted">click to zoom in</span>` : "");
        tip.style.display = "block";
        const r = stage.getBoundingClientRect();
        tip.style.left = event.clientX - r.left + 12 + "px";
        tip.style.top = event.clientY - r.top + 12 + "px";
      })
      .on("mouseleave", () => (tip.style.display = "none"))
      .on("click", (event, d) => {
        if (d.children) {
          path.push(d.data);
          draw();
        } else {
          const level = path[1] ? path[1].name : focusData.name;
          window.sm64CopyQuery(leafQuery(level, d.data.name));
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
        const name = tilesAreObjLists ? catLabel(d.data.name) : strip(d.data.name);
        return (
          `<div class="tm-label" style="color:${fg}">` +
          `<span class="tm-name">${escapeHtml(name)}</span>` +
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
      if (!treeRootData) treeRootData = { name: "root", children: loadTree() };
      path = [treeRootData];
      draw();
    },
  };
})();
