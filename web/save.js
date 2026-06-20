"use strict";

// ---------------------------------------------------------------------------
// Save tab: the 0x200-byte EEPROM save buffer as a nested, drillable layout.
//
// One consistent idiom throughout (the same rounded, tinted, byte-proportional
// tiles as the Treemap tab): every level is a full-width bar whose tiles divide
// it in offset order, sized to scale. Clicking a tile that has contents drills
// in -- but append-only: the new level is appended below and the ancestors stay
// visible, with a funnel connecting the opened tile to its expansion. A
// breadcrumb (and re-clicking an ancestor tile) drills back up. Everything is a
// container until it bottoms out: SaveBuffer -> files -> File A -> SaveFile ->
// courseStars -> a single course's byte, or flags -> one of 32 bits.
//
// Nothing is hand-placed: the tree, every size and offset, and the bit gaps all
// come from save_struct / save_field / save_flag.
// ---------------------------------------------------------------------------

(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();

  let inited = false;
  let data = null; // { structs, fieldsBy, flagsBy }
  let root = null; // the SaveBuffer hierarchy node
  let path = []; // root chain of nodes currently drilled into

  // layout
  const PADX = 16, PADTOP = 14, BAND = 18, BARH = 58, VGAP = 50;

  // Same palette + tinting as the Treemap tab, so the two tabs read alike.
  const PALETTE = [
    "#4dabf7", "#69db7c", "#ffa94d", "#f783ac", "#38d9a9",
    "#ffd43b", "#a9e34b", "#3bc9db", "#748ffc", "#da77f2", "#ff8787",
  ];
  // Colour tracks a tile's "kind" (one stable scale across the whole diagram):
  // C type for fields/elements, flag category for bits, plus greys for the
  // structural and empty kinds.
  const KIND_ORDER = [
    "struct", "u32", "u16", "u8", "s16", "Vec3s",
    "caps & keys", "doors", "lost-cap thieves", "secret stars", "world state",
  ];
  const scale = d3.scaleOrdinal(PALETTE).domain(KIND_ORDER);
  // Kinds that get a fixed hue rather than one off the cycling type scale:
  // the structural greys, and the star-byte bits.
  const FIXED = {
    padding: "#c7cdda",
    unused: "#eceef4",
    "act star": "#f6c945",
    "100-coin star": "#ff922b",
    cannon: "#22b8cf",
  };
  const colorOf = (kind) => FIXED[kind] || scale(kind);
  const tint = (hex, t) => d3.interpolateRgb(hex, "#ffffff")(t);
  function textOn(bg) {
    const c = d3.color(bg).rgb();
    return (0.299 * c.r + 0.587 * c.g + 0.114 * c.b) / 255 > 0.62 ? "#1d2330" : "#fff";
  }

  function flagCat(name) {
    const n = name.replace(/^SAVE_FLAG_/, "");
    if (n.startsWith("HAVE_")) return "caps & keys";
    if (n.startsWith("UNLOCKED_")) return "doors";
    if (n.startsWith("CAP_ON_")) return "lost-cap thieves";
    if (n.startsWith("COLLECTED_")) return "secret stars";
    return "world state";
  }
  const stripFlag = (n) => n.replace(/^SAVE_FLAG_/, "");
  const escapeHtml = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const hexb = (n) => "0x" + n.toString(16).toUpperCase().padStart(2, "0");
  const sqlStr = (s) => String(s).replace(/'/g, "''");

  // --- tiny SVG helper -----------------------------------------------------
  function mk(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }
  function txt(parent, x, y, str, cls) {
    const t = mk("text", { x, y, class: cls }, parent);
    t.textContent = str;
    return t;
  }

  // A wrapping, ellipsizing label inside the tile (a foreignObject + HTML div,
  // the same approach as the Treemap tab) so even narrow tiles stay labelled:
  // the name wraps and, if it still cannot fit, elides rather than vanishing.
  function addLabel(g, n, seg, top, fill) {
    if (seg.w < 11) return;
    const fo = mk(
      "foreignObject",
      { x: seg.x + 1, y: top, width: Math.max(0, seg.w - 2), height: BARH, class: "save-fo" },
      g
    );
    const div = document.createElement("div");
    div.className = "save-lab";
    div.style.color = textOn(fill);
    const nm = document.createElement("span");
    nm.className = "nm";
    nm.textContent = n.label || "—";
    div.appendChild(nm);
    if (n.sub) {
      const sb = document.createElement("span");
      sb.className = "sb";
      sb.textContent = n.sub;
      div.appendChild(sb);
    }
    fo.appendChild(div);
  }

  // --- data ----------------------------------------------------------------
  function load() {
    const rows = (sql) => {
      const r = sdb().exec(sql);
      return r.length ? r[0].values : [];
    };
    const structs = {};
    rows("SELECT struct_name, size, align, doc FROM save_struct").forEach(
      ([name, size, align, doc]) => (structs[name] = { name, size, align, doc })
    );
    const fieldsBy = {};
    rows(
      "SELECT struct_name, seq, field_name, type_name, dims, count, elem_size, " +
        "offset, size, is_struct, doc FROM save_field ORDER BY struct_name, seq"
    ).forEach((r) => {
      const f = {
        struct: r[0], seq: r[1], name: r[2], type: r[3], dims: r[4],
        count: r[5], elemSize: r[6], offset: r[7], size: r[8],
        isStruct: !!r[9], doc: r[10],
      };
      (fieldsBy[f.struct] = fieldsBy[f.struct] || []).push(f);
    });
    const flagsBy = {};
    rows("SELECT flag_group, bit, flag_name, mask FROM save_flag ORDER BY bit").forEach(
      ([group, bit, name, mask]) => {
        (flagsBy[group] = flagsBy[group] || []).push({ bit, name, mask });
      }
    );
    // Course names (rowid order == enum order: COURSE_NONE, BOB, WF, ... bonus)
    // so courseStars[i] / courseCoinScores[i] (indexed by courseNum-1) label as
    // the (i+1)-th course. Plus each course's six act-star names, to label the
    // star byte's bits.
    let courses = [];
    let starsBy = {};
    try {
      courses = rows("SELECT course_name, display_name, is_bonus FROM course").map(
        ([course_name, display_name, is_bonus]) => ({ course_name, display_name, is_bonus })
      );
      rows("SELECT course_name, act, name FROM star WHERE kind = 'main'").forEach(
        ([course_name, act, name]) => {
          (starsBy[course_name] = starsBy[course_name] || {})[act] = name;
        }
      );
    } catch (e) {
      /* older DBs may lack these; star/course labels just fall back to indices */
    }
    return { structs, fieldsBy, flagsBy, courses, starsBy };
  }

  // --- build the hierarchy -------------------------------------------------
  // Each node: { label, sub, kind, colorKey, size, offset, doc, owner, query,
  //              children:[]|null }. size is used only relative to siblings, so
  //              bits (32 of them) just use 1 apiece.
  function buildStruct(name, label, sub, offset) {
    const st = data.structs[name];
    const fields = data.fieldsBy[name] || [];
    return {
      label: label || name,
      sub: sub || (label && label !== name ? name : null),
      kind: "struct",
      colorKey: "struct",
      size: st ? st.size : fields.reduce((a, f) => a + f.size, 0),
      offset: offset || 0,
      doc: st ? st.doc : null,
      owner: name,
      children: fields.map((f) => buildField(f, name)),
    };
  }

  function buildField(f, owner) {
    const colorKey = f.isStruct ? "struct" : f.name === "filler" ? "padding" : f.type;
    const base = {
      label: f.name,
      sub: f.type,
      kind: "field",
      colorKey,
      size: f.size,
      offset: f.offset,
      doc: f.doc,
      owner,
      query: `-- ${owner}.${f.name}\nSELECT * FROM save_field WHERE struct_name = '${sqlStr(
        owner
      )}' AND field_name = '${sqlStr(f.name)}';`,
      children: null,
    };
    if (data.flagsBy[f.name]) {
      base.children = buildBits(data.flagsBy[f.name]);
    } else if (f.isStruct && f.count === 1) {
      base.children = buildStruct(f.type).children; // inline the sub-struct's fields
    } else if (f.isStruct && f.count > 1) {
      base.children = instances(f);
    } else if (f.count > 1) {
      base.children = elements(f, owner);
    }
    return base;
  }

  // Struct array -> one struct per element. files[4][2] reads as 4 save slots
  // (A-D) each with a primary + backup copy; menuData[2] as two copies.
  function instances(f) {
    const dims = f.dims ? f.dims.split(",").map(Number) : [f.count];
    const copies = dims.length > 1 ? dims[1] : dims[0];
    const isFiles = f.name === "files";
    const out = [];
    for (let i = 0; i < f.count; i++) {
      const slot = Math.floor(i / copies);
      const copy = i % copies;
      const label = isFiles ? `File ${"ABCD"[slot] || slot}` : "Menu";
      const sub = copies === 2 ? (copy === 0 ? "primary" : "backup") : `[${i}]`;
      out.push(buildStruct(f.type, label, sub, f.offset + i * f.elemSize));
    }
    return out;
  }

  // Primitive array -> one tile per element. courseStars / courseCoinScores are
  // indexed by courseNum-1, so element i is the (i+1)-th course (courses[0] is
  // COURSE_NONE); label each with that course's name. A courseStars byte further
  // drills into its 8 star/cannon bits.
  function elements(f, owner) {
    const isStars = f.name === "courseStars";
    const isCoins = f.name === "courseCoinScores";
    const out = [];
    for (let i = 0; i < f.count; i++) {
      const course = isStars || isCoins ? data.courses[i + 1] : null;
      out.push({
        label: course ? course.display_name : `[${i}]`,
        sub: isCoins ? "max coins" : isStars ? "star flags" : `${f.type} [${i}]`,
        kind: "element",
        colorKey: f.type,
        size: f.elemSize,
        offset: f.offset + i * f.elemSize,
        doc: course ? `${owner}.${f.name}[${i}] — ${course.course_name}` : null,
        owner,
        query: `-- ${owner}.${f.name}[${i}]${course ? ` (${course.course_name})` : ""}\nSELECT * FROM save_field WHERE struct_name = '${sqlStr(
          owner
        )}' AND field_name = '${sqlStr(f.name)}';`,
        children: isStars ? buildStarBits(i) : null,
      });
    }
    return out;
  }

  // A course's star byte: bits 0-5 are its six act stars (named from the star
  // table), bit 6 the 100-coin star, bit 7 the cannon-open flag -- which, per the
  // decomp's "byte following each course" quirk, actually unlocks the *previous*
  // course's cannon (cannon of course c is courseStars[c] bit 7, but stars of
  // course c are courseStars[c-1]).
  function buildStarBits(byteIndex) {
    const starCourse = data.courses[byteIndex + 1]; // whose stars bits 0-6 are
    const cannonCourse = data.courses[byteIndex]; // whose cannon bit 7 holds
    const named = (starCourse && data.starsBy[starCourse.course_name]) || {};
    const cannonReal = cannonCourse && cannonCourse.course_name !== "COURSE_NONE";
    const bits = [];
    for (let b = 0; b < 8; b++) {
      let node;
      if (b <= 5) {
        const act = b + 1;
        node = {
          label: named[act] || `Star ${act}`,
          sub: `act ${act}`,
          colorKey: "act star",
          doc: starCourse ? `${starCourse.display_name} · star ${act}` : null,
        };
      } else if (b === 6) {
        node = {
          label: "100-coin Star",
          sub: "bit 6",
          colorKey: "100-coin star",
          doc: starCourse ? `${starCourse.display_name} · 100-coin star` : null,
        };
      } else {
        node = {
          label: "Cannon",
          sub: cannonReal ? cannonCourse.display_name : "(unused)",
          colorKey: "cannon",
          doc:
            "Cannon-open flag. SM64 quirk: bit 7 of a course's byte unlocks the " +
            "cannon for the *previous* course — the decomp notes it lives in " +
            `"the byte following each course"${cannonReal ? ` (here: ${cannonCourse.display_name})` : ""}.`,
        };
      }
      bits.push({ ...node, kind: "bit", size: 1, offset: b, owner: null, query: null, children: null });
    }
    return bits;
  }

  // The flags u32 -> 32 bit tiles; bits with no SAVE_FLAG are the gaps.
  function buildBits(flags) {
    const byBit = {};
    flags.forEach((fl) => (byBit[fl.bit] = fl));
    const out = [];
    for (let b = 0; b < 32; b++) {
      const fl = byBit[b];
      out.push(
        fl
          ? {
              label: stripFlag(fl.name),
              sub: `bit ${b}`,
              kind: "bit",
              colorKey: flagCat(fl.name),
              size: 1,
              offset: b,
              doc: `mask 0x${fl.mask.toString(16).toUpperCase().padStart(8, "0")} · ${flagCat(
                fl.name
              )}`,
              owner: null,
              query: `-- ${fl.name}\nSELECT * FROM save_flag WHERE flag_name = '${sqlStr(
                fl.name
              )}';`,
              children: null,
            }
          : {
              label: "",
              sub: `bit ${b}`,
              kind: "unused",
              colorKey: "unused",
              size: 1,
              offset: b,
              doc: "no flag defined (unused bit)",
              owner: null,
              query: null,
              children: null,
            }
      );
    }
    return out;
  }

  // --- tooltip -------------------------------------------------------------
  function showTip(html, evt) {
    const tip = el("save-tooltip");
    const stage = el("save-stage");
    tip.innerHTML = html;
    tip.style.display = "block";
    const r = stage.getBoundingClientRect();
    tip.style.left = evt.clientX - r.left + 14 + "px";
    tip.style.top = evt.clientY - r.top + 14 + "px";
  }
  const hideTip = () => (el("save-tooltip").style.display = "none");

  function tipHtml(node) {
    const head = node.sub ? `${node.label || "—"} <span class="muted">${escapeHtml(node.sub)}</span>` : node.label || "—";
    const where =
      node.kind === "bit" || node.kind === "unused"
        ? `bit ${node.offset}`
        : `@ ${hexb(node.offset)} · ${node.size} byte${node.size === 1 ? "" : "s"}`;
    const action = node.children
      ? "click to drill in ↓"
      : node.query
      ? "click to copy its query"
      : "";
    return (
      `<strong>${head}</strong>` +
      `<br><span class="muted">${escapeHtml(where)}</span>` +
      (node.doc ? `<br>${escapeHtml(node.doc)}` : "") +
      (action ? `<br><span class="muted">${action}</span>` : "")
    );
  }

  // --- breadcrumb ----------------------------------------------------------
  function buildBreadcrumb() {
    const bc = el("save-breadcrumb");
    bc.innerHTML = "";
    path.forEach((node, i) => {
      if (i) {
        const sep = document.createElement("span");
        sep.className = "save-sep";
        sep.textContent = "▸";
        bc.appendChild(sep);
      }
      const last = i === path.length - 1;
      const b = document.createElement("button");
      b.className = "save-crumb" + (last ? " current" : "");
      // Only a file/menu instance needs its copy (primary/backup) in the crumb.
      b.textContent = node.label + (node.kind === "struct" && node.sub ? ` ${node.sub}` : "");
      if (!last)
        b.addEventListener("click", () => {
          path = path.slice(0, i + 1);
          render();
        });
      bc.appendChild(b);
    });
  }

  // --- fills ---------------------------------------------------------------
  // Leaves are vivid; a container is a lighter tint (like the treemap frames),
  // so "drillable" reads at a glance; the opened tile is shown full-strength.
  function fillFor(node, selected) {
    const base = colorOf(node.colorKey);
    if (node.kind === "unused") return base;
    if (node.children && !selected) return tint(base, 0.5);
    return base;
  }

  function describe(node) {
    const c = node.children || [];
    if (node === root) return `${node.label} · ${node.size} bytes (0x200)`;
    const kid = c[0] ? c[0].kind : null;
    if (kid === "bit") return `${node.label} · 32 bits @ ${hexb(node.offset)}`;
    if (kid === "element") return `${node.label}[${c.length}] · ${c.length} × ${c[0].sub}`;
    if (kid === "struct") return `${node.label} · ${c.length} × ${node.sub}`;
    // struct fields (a file/menu instance, or an inline sub-struct like signature):
    // name the struct the fields actually belong to (the children's owner).
    const owner = c[0] ? c[0].owner : node.owner;
    const head = node.kind === "struct" && node.sub ? `${node.label} ${node.sub}` : node.label;
    return `${head} · ${owner} fields`;
  }

  // --- render --------------------------------------------------------------
  function render() {
    const svg = el("save-svg");
    const stage = el("save-stage");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const W = Math.max(720, stage.clientWidth || 960);
    const innerW = W - 2 * PADX;

    buildBreadcrumb();

    // 1) lay out every bar (geometry only) so connectors can be drawn behind.
    const bars = [];
    let y = PADTOP;
    for (let k = 0; k < path.length; k++) {
      const node = path[k];
      const kids = node.children || [];
      const top = y + BAND;
      const total = Math.max(1, kids.reduce((a, c) => a + c.size, 0));
      let x = PADX;
      const segs = kids.map((c) => {
        const w = (innerW * c.size) / total;
        const seg = { node: c, x, w, selected: path[k + 1] === c };
        x += w;
        return seg;
      });
      bars.push({ node, bandY: y + 12, top, segs, sel: segs.find((s) => s.selected) });
      y = top + BARH + VGAP;
    }
    const height = y - VGAP + PADTOP;

    // 2) connectors: a curvy funnel from an opened tile down to its bar. Each
    // side is a vertical cubic Bezier (control points at the midpoint height) so
    // the expansion reads as a smooth zoom rather than a hard trapezoid.
    for (let k = 0; k < bars.length - 1; k++) {
      const sel = bars[k].sel;
      if (!sel) continue;
      const yTop = bars[k].top + BARH;
      const yBot = bars[k + 1].top;
      const ym = (yTop + yBot) / 2;
      const lx = sel.x, rx = sel.x + sel.w; // opened tile edges
      const bl = PADX, br = PADX + innerW; // child bar edges
      const fill = colorOf(sel.node.colorKey);
      mk(
        "path",
        {
          d:
            `M${lx},${yTop} C${lx},${ym} ${bl},${ym} ${bl},${yBot} ` +
            `L${br},${yBot} C${br},${ym} ${rx},${ym} ${rx},${yTop} Z`,
          fill,
          "fill-opacity": 0.1,
          stroke: fill,
          "stroke-opacity": 0.35,
          "stroke-width": 1,
        },
        svg
      );
    }

    // 3) the bars themselves.
    bars.forEach((bar) => {
      txt(svg, PADX, bar.bandY, describe(bar.node), "save-bandlabel");
      bar.segs.forEach((seg) => {
        const n = seg.node;
        const fill = fillFor(n, seg.selected);
        const drill = !!n.children;
        const g = mk(
          "g",
          {
            class:
              "save-seg" +
              (seg.selected ? " sel" : "") +
              (drill || n.query ? " link" : "") +
              (n.kind === "unused" ? " unused" : ""),
          },
          svg
        );
        mk(
          "rect",
          { x: seg.x + 0.5, y: bar.top, width: Math.max(0, seg.w - 1), height: BARH, rx: 4, fill },
          g
        );
        addLabel(g, n, seg, bar.top, fill);
        const html = tipHtml(n);
        g.addEventListener("mousemove", (e) => showTip(html, e));
        g.addEventListener("mouseleave", hideTip);
        g.addEventListener("click", () => onPick(bar, seg));
      });
    });

    svg.setAttribute("width", W);
    svg.setAttribute("height", Math.ceil(height));
    svg.setAttribute("viewBox", `0 0 ${W} ${Math.ceil(height)}`);
    el("save-status").textContent =
      `${path[path.length - 1].label} · whole EEPROM = ${root.size} bytes`;
  }

  function onPick(bar, seg) {
    const n = seg.node;
    const depth = path.indexOf(bar.node);
    if (n.children) {
      path = path.slice(0, depth + 1).concat(n); // append-only drill
      render();
    } else if (n.query) {
      window.sm64CopyQuery(n.query);
    }
  }

  function ensureInit() {
    if (inited) return;
    inited = true;
    let t = null;
    window.addEventListener("resize", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        if (el("tab-save").classList.contains("active") && data) render();
      }, 150);
    });
  }

  // Default drill: SaveBuffer -> files -> File A (primary), so the SaveFile
  // struct (with flags + courseStars to drill) is on screen immediately.
  function defaultPath() {
    const p = [root];
    const files = (root.children || []).find((c) => c.label === "files");
    if (files && files.children && files.children.length) {
      p.push(files, files.children[0]);
    }
    return p;
  }

  window.SM64Save = {
    onShow() {
      ensureInit();
      if (!data) {
        try {
          data = load();
          if (!data.structs.SaveBuffer) throw new Error("no SaveBuffer");
          root = buildStruct("SaveBuffer");
          path = defaultPath();
        } catch (err) {
          el("save-status").textContent = "Save layout tables not in this database.";
          console.error(err);
          return;
        }
      }
      render();
    },
  };
})();
