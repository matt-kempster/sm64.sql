"use strict";

// ---------------------------------------------------------------------------
// Save tab: a memory-map block diagram of the 0x200-byte EEPROM save buffer.
//
// Three stacked sections, all computed from save_struct / save_field / save_flag:
//   1. EEPROM overview  -- the whole SaveBuffer: 4 files x 2 copies + 2 menu
//      copies, drawn as labelled blocks (the redundancy/backup structure).
//   2. Struct detail    -- the selected struct laid out one cell per byte at its
//      true offset (16 bytes/row), fields coloured and sized to scale.
//   3. Flags ribbon     -- the SaveFile.flags u32 exploded into its 32 bits: the
//      named SAVE_FLAG_* bits plus the gaps where no flag is defined.
//
// Clicking a block in the overview (or a struct-typed field in the detail grid)
// selects which struct the lower sections describe. Defaults to SaveFile, the
// interesting one. Nothing here is hand-placed: offsets, sizes and the bit gaps
// all come straight from the database.
// ---------------------------------------------------------------------------

(function () {
  const SVG_NS = "http://www.w3.org/2000/svg";
  const el = (id) => document.getElementById(id);
  const sdb = () => window.sm64db();

  let inited = false;
  let data = null; // { structs, fieldsBy, flagsBy }
  let selected = "SaveFile";

  const COLS = 16; // bytes per row in the byte grid
  const CELL = 22; // px per byte cell
  const PAD = 18; // section padding
  const RULER = 52; // left gutter for offset labels

  // Field palette (skipping the flags accent, which is reserved). Padding/filler
  // is always neutral grey; the bit-packed flags word gets the purple accent so
  // it ties to the ribbon below.
  const PALETTE = [
    "#4dabf7", "#69db7c", "#ffa94d", "#f783ac", "#38d9a9",
    "#ffd43b", "#a9e34b", "#3bc9db", "#748ffc", "#ff8787",
  ];
  const FLAGS_ACCENT = "#9775fa";
  const PAD_FILL = "#c7cdda";

  // Flag categories -> colour, so the ribbon reads like a register diagram.
  const FLAG_CATS = {
    item: { color: "#ffd43b", label: "caps & keys" },
    door: { color: "#4dabf7", label: "doors" },
    cap: { color: "#ff8787", label: "lost-cap thieves" },
    star: { color: "#69db7c", label: "secret stars" },
    misc: { color: "#b197fc", label: "world state" },
  };
  function flagCat(name) {
    const n = name.replace(/^SAVE_FLAG_/, "");
    if (n.startsWith("HAVE_")) return "item";
    if (n.startsWith("UNLOCKED_")) return "door";
    if (n.startsWith("CAP_ON_")) return "cap";
    if (n.startsWith("COLLECTED_")) return "star";
    return "misc";
  }
  const stripFlag = (n) => n.replace(/^SAVE_FLAG_/, "");

  const escapeHtml = (s) =>
    String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  const hex = (n) => "0x" + n.toString(16).toUpperCase().padStart(2, "0");

  // --- tiny SVG helper -----------------------------------------------------
  function mk(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(node);
    return node;
  }
  function text(parent, x, y, str, cls) {
    const t = mk("text", { x, y, class: cls || "save-label" }, parent);
    t.textContent = str;
    return t;
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
    rows(
      "SELECT flag_group, bit, flag_name, mask FROM save_flag ORDER BY bit"
    ).forEach(([group, bit, name, mask]) => {
      (flagsBy[group] = flagsBy[group] || []).push({ bit, name, mask });
    });
    return { structs, fieldsBy, flagsBy };
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

  function hoverable(node, html) {
    node.addEventListener("mousemove", (e) => showTip(html, e));
    node.addEventListener("mouseleave", hideTip);
  }

  // --- section 1: EEPROM overview -----------------------------------------
  // Returns the y just below this section.
  function drawOverview(svg, width, y0) {
    const root = data.structs.SaveBuffer;
    if (!root) return y0;
    let y = y0 + PAD;
    text(svg, PAD, y, `EEPROM — SaveBuffer · ${root.size} bytes (0x200)`, "save-title");
    y += 14;

    const fields = data.fieldsBy.SaveBuffer || [];
    const BW = 104, BH = 50, GAP = 10;
    let x = PAD;
    const top = y + 8;

    fields.forEach((f) => {
      if (!f.isStruct) return;
      const dims = f.dims ? f.dims.split(",").map(Number) : [f.count];
      // files[4][2] -> 4 slots (columns) x 2 copies (rows); menuData[2] -> 1 x 2.
      const slots = dims.length > 1 ? dims[0] : 1;
      const copies = dims.length > 1 ? dims[1] : dims[0];
      const groupLabel = f.name === "files" ? "Save files (4 × 2 backup)" : "Menu data (× 2)";
      text(svg, x, top - 6, groupLabel, "save-grouplabel");
      for (let s = 0; s < slots; s++) {
        for (let c = 0; c < copies; c++) {
          const idx = s * copies + c;
          const bx = x + s * (BW + GAP);
          const by = top + c * (BH + GAP);
          const off = f.offset + idx * f.elemSize;
          const sel = f.type === selected;
          const g = mk("g", { class: "save-block" + (sel ? " sel" : "") }, svg);
          mk("rect", { x: bx, y: by, width: BW, height: BH, rx: 4, class: "save-block-rect" }, g);
          // a thin checksum tick at the block's tail (every struct ends in one)
          mk("rect", { x: bx + BW - 7, y: by, width: 7, height: BH, rx: 0, class: "save-chk" }, g);
          const slotName = f.name === "files" ? "ABCD"[s] : "menu";
          const label = f.name === "files" ? `File ${slotName}` : "Menu";
          text(svg, bx + 8, by + 19, label, "save-block-name");
          text(svg, bx + 8, by + 34, c === 0 ? "primary" : "backup", "save-block-sub");
          text(svg, bx + 8, by + 45, hex(off), "save-block-off");
          hoverable(
            g,
            `<strong>${escapeHtml(f.type)}</strong> — ${label} ${c === 0 ? "primary" : "backup"}` +
              `<br><span class="muted">@ ${hex(off)} · ${f.elemSize} bytes · ends in a 4-byte checksum</span>` +
              `<br><span class="muted">click to lay out its bytes ↓</span>`
          );
          g.addEventListener("click", () => {
            if (data.structs[f.type]) {
              selected = f.type;
              render();
            }
          });
        }
      }
      x += slots * (BW + GAP) + 24;
    });
    return top + 2 * BH + GAP + PAD;
  }

  // --- byte-grid geometry --------------------------------------------------
  // Split a [offset, offset+size) span into per-row segments of the 16-wide grid.
  function segments(offset, size) {
    const segs = [];
    let b = offset;
    const end = offset + size;
    while (b < end) {
      const row = Math.floor(b / COLS);
      const col = b % COLS;
      const take = Math.min(COLS - col, end - b);
      segs.push({ row, col, len: take });
      b += take;
    }
    return segs;
  }

  // --- section 2: struct byte grid ----------------------------------------
  function drawDetail(svg, y0) {
    const st = data.structs[selected];
    const fields = data.fieldsBy[selected] || [];
    if (!st) return y0;
    let y = y0;
    text(
      svg, PAD, y,
      `${st.name} · ${st.size} bytes (0x${st.size.toString(16).toUpperCase()})`,
      "save-title"
    );
    y += 6;
    if (st.doc) {
      const d = text(svg, PAD, y + 14, st.doc, "save-doc");
      // crude truncation so a long note doesn't overflow
      if (st.doc.length > 96) d.textContent = st.doc.slice(0, 95) + "…";
      y += 12;
    }
    const gridY = y + 18;
    const rows = Math.ceil(st.size / COLS);

    // faint cell grid + offset ruler
    for (let r = 0; r < rows; r++) {
      text(svg, RULER - 10, gridY + r * CELL + 15, hex(r * COLS), "save-ruler");
    }

    let palette = 0;
    fields.forEach((f) => {
      let fill = PALETTE[palette++ % PALETTE.length];
      if (f.name === "flags") fill = FLAGS_ACCENT;
      if (f.name === "filler" || f.type === "filler") fill = PAD_FILL;
      const isFlags = f.name === "flags";
      const clickable = f.isStruct && data.structs[f.type];
      const g = mk(
        "g",
        { class: "save-field" + (isFlags ? " flags" : "") + (clickable ? " link" : "") },
        svg
      );
      const segs = segments(f.offset, f.size);
      segs.forEach((seg) => {
        const x = RULER + seg.col * CELL;
        const yy = gridY + seg.row * CELL;
        mk("rect", {
          x: x + 1, y: yy + 1, width: seg.len * CELL - 2, height: CELL - 2, rx: 2,
          fill, class: "save-cell",
        }, g);
      });
      // label in the widest segment, if it fits
      const wide = segs.reduce((a, b) => (b.len > a.len ? b : a), segs[0]);
      const lx = RULER + wide.col * CELL + 4;
      const ly = gridY + wide.row * CELL + 15;
      const tag = f.count > 1 ? `${f.name}[${f.count}]` : f.name;
      if (wide.len * CELL > tag.length * 6.2 + 6)
        text(svg, lx, ly, tag, "save-field-name");
      hoverable(
        g,
        `<strong>${escapeHtml(tag)}</strong> <span class="muted">${escapeHtml(f.type)}</span>` +
          `<br><span class="muted">@ ${hex(f.offset)} · ${f.size} byte${f.size === 1 ? "" : "s"}` +
          (f.count > 1 ? ` · ${f.count} × ${f.elemSize}` : "") +
          `</span>` +
          (f.doc ? `<br>${escapeHtml(f.doc)}` : "") +
          (f.isStruct ? `<br><span class="muted">click to open ${escapeHtml(f.type)} ↓</span>` : "") +
          (isFlags ? `<br><span class="muted">exploded into 32 bits below ↓</span>` : "")
      );
      if (f.isStruct && data.structs[f.type])
        g.addEventListener("click", () => {
          selected = f.type;
          render();
        });
    });
    return gridY + rows * CELL + PAD;
  }

  // --- section 3: flags ribbon --------------------------------------------
  function drawRibbon(svg, width, y0) {
    const fields = data.fieldsBy[selected] || [];
    const flagField = fields.find((f) => data.flagsBy[f.name]);
    if (!flagField) return y0;
    const flags = data.flagsBy[flagField.name];
    const byBit = {};
    flags.forEach((f) => (byBit[f.bit] = f));
    const NBITS = 32;

    let y = y0;
    text(
      svg, PAD, y,
      `${flagField.name} · u32 @ ${hex(flagField.offset)} · 32 bits`,
      "save-title"
    );
    y += 6;
    text(
      svg, PAD, y + 13,
      "Each set bit is one piece of progress. Empty cells are bits no flag uses.",
      "save-doc"
    );
    const top = y + 26;

    // a strip of 32 cells, bit 0 on the left
    const stripW = width - 2 * PAD;
    const bw = Math.min(40, stripW / NBITS);
    for (let bit = 0; bit < NBITS; bit++) {
      const x = PAD + bit * bw;
      const fl = byBit[bit];
      const cat = fl ? flagCat(fl.name) : null;
      const fill = fl ? FLAG_CATS[cat].color : "none";
      const g = mk("g", { class: "save-bit" + (fl ? "" : " unused") }, svg);
      mk("rect", { x, y: top, width: bw - 2, height: 30, rx: 2, fill, class: "save-bit-rect" }, g);
      text(svg, x + (bw - 2) / 2, top + 19, String(bit), fl ? "save-bit-num" : "save-bit-num dim");
      if (fl)
        hoverable(
          g,
          `<strong>${escapeHtml(stripFlag(fl.name))}</strong>` +
            `<br><span class="muted">bit ${fl.bit} · mask 0x${fl.mask
              .toString(16)
              .toUpperCase()
              .padStart(8, "0")} · ${FLAG_CATS[cat].label}</span>`
        );
      else hoverable(g, `<span class="muted">bit ${bit} — unused</span>`);
    }
    let yy = top + 44;
    text(svg, PAD, yy, `${flags.length} named bits · ${NBITS - flags.length} unused`, "save-grouplabel");
    yy += 10;

    // legend: named bits grouped by category, in columns
    const COLW = 232;
    const perCol = Math.ceil(flags.length / Math.max(1, Math.floor((width - 2 * PAD) / COLW)));
    let i = 0;
    const ordered = flags.slice().sort((a, b) => {
      const ca = flagCat(a.name), cb = flagCat(b.name);
      return ca === cb ? a.bit - b.bit : ca.localeCompare(cb);
    });
    ordered.forEach((fl) => {
      const col = Math.floor(i / perCol);
      const row = i % perCol;
      const x = PAD + col * COLW;
      const ly = yy + 12 + row * 18;
      const cat = flagCat(fl.name);
      mk("rect", { x, y: ly - 9, width: 11, height: 11, rx: 2, fill: FLAG_CATS[cat].color, class: "save-legend-sw" }, svg);
      text(svg, x + 17, ly, `${fl.bit}`, "save-legend-bit");
      text(svg, x + 36, ly, stripFlag(fl.name), "save-legend-name");
      i++;
    });
    return yy + 12 + perCol * 18 + PAD;
  }

  // --- render --------------------------------------------------------------
  function render() {
    const svg = el("save-svg");
    const stage = el("save-stage");
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    const width = Math.max(720, stage.clientWidth || 960);

    let y = drawOverview(svg, width, 0);
    y = drawDetail(svg, y);
    y = drawRibbon(svg, width, y);

    svg.setAttribute("width", width);
    svg.setAttribute("height", Math.ceil(y));
    svg.setAttribute("viewBox", `0 0 ${width} ${Math.ceil(y)}`);

    const st = data.structs[selected];
    const buf = data.structs.SaveBuffer;
    el("save-status").textContent =
      st && buf
        ? `${selected} · ${st.size} bytes · whole EEPROM = ${buf.size} bytes`
        : "";
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

  window.SM64Save = {
    onShow() {
      ensureInit();
      if (!data) {
        try {
          data = load();
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
