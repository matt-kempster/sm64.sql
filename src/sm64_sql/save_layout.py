import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from sm64_sql.parse_utils import (
    evaluate_int,
    extract_macro_args,
    parse_c_defines,
    strip_comments,
)

# The save format lives in one header; the alias types it uses (Vec3s) and the
# course counts its arrays are sized by live elsewhere in the tree.
SAVE_FILE_H = ("src", "game", "save_file.h")
TYPES_H = ("include", "types.h")
COURSE_DEFINES = ("levels", "course_defines.h")

# The struct that maps 1:1 onto the on-cartridge EEPROM. Everything the save
# block diagram shows is this struct and the structs reachable from it; anything
# else in the header (WarpCheckpoint -- runtime only) is intentionally not part
# of the saved layout and is left out.
EEPROM_ROOT = "SaveBuffer"

# N64 (MIPS o32, big-endian) primitive sizes/alignments. Every scalar in the
# save structs is one of these or a typedef alias resolved from include/types.h.
PRIMITIVES: Dict[str, Tuple[int, int]] = {
    "u8": (1, 1),
    "s8": (1, 1),
    "char": (1, 1),
    "u16": (2, 2),
    "s16": (2, 2),
    "u32": (4, 4),
    "s32": (4, 4),
    "f32": (4, 4),
    "int": (4, 4),
    "float": (4, 4),
    "u64": (8, 8),
    "s64": (8, 8),
    "f64": (8, 8),
    "double": (8, 8),
}

# Regional builds vary the layout (EU adds a `language` field and a different
# pad); treating these as undefined selects the common 0x200 US/JP layout.
_FALSE_MACROS = ("VERSION_EU", "VERSION_SH", "VERSION_CN")

_STRUCT_START = re.compile(r"^struct\s+(\w+)\s*\{")
_MEMBER_RE = re.compile(
    r"^(?:struct\s+)?(?P<type>[A-Za-z_]\w*)\s+(?P<name>[A-Za-z_]\w*)"
    r"\s*(?P<dims>(?:\[[^\]]*\])*)\s*;"
)
_TYPEDEF_RE = re.compile(
    r"^typedef\s+(?P<base>[A-Za-z_]\w*)\s+(?P<name>[A-Za-z_]\w*)"
    r"\s*(?P<arr>(?:\[\d+\])*)\s*;"
)


@dataclass
class SM64SaveStruct:
    """One C struct that makes up the EEPROM save buffer, with its computed size.

    ``size`` is ``sizeof`` in bytes under the N64 ABI (natural alignment); the
    root ``SaveBuffer`` is exactly ``EEPROM_SIZE`` (0x200) -- the invariant the
    whole layout is checked against.
    """

    struct_name: str
    size: int  # sizeof, in bytes
    align: int  # alignment in bytes (its widest member)
    doc: Optional[str]  # the doc comment above the struct, if any


@dataclass
class SM64SaveField:
    """One member of a save struct, placed at its computed byte offset.

    ``dims`` keeps the declared array shape (``"4,2"`` for ``files[4][2]`` --
    4 save slots x 2 backup copies) so the diagram can draw the redundancy;
    ``count`` is their product. ``elem_size`` is the size of one element and
    ``size`` the field's total span (``elem_size * count``).
    """

    struct_name: str
    seq: int  # declaration order within the struct
    field_name: str
    type_name: str  # the element type spelling (u8, u32, Vec3s, SaveFile, ...)
    dims: str  # array shape, e.g. "" (scalar), "25", or "4,2"; product == count
    count: int  # number of elements (1 for a scalar)
    elem_size: int  # bytes per element
    offset: int  # byte offset within the struct
    size: int  # total bytes the field spans
    is_struct: bool  # whether type_name is itself a save struct (drill-in target)
    doc: Optional[str]  # the comment attached to the field, if any


@dataclass
class SM64SaveFlag:
    """One bit of a bit-packed save field (the ``SaveFile.flags`` u32).

    ``flag_group`` is the field the bit belongs to (``"flags"``); ``bit`` is its
    index 0-31 and ``mask`` the ``1 << bit`` value. Bits with no ``#define`` are
    simply absent -- the gaps in the numbering are the unused bits. (``group`` is
    a SQL keyword, hence ``flag_group``.)
    """

    flag_group: str
    bit: int
    flag_name: str
    mask: int


@dataclass
class ParsedSaveLayout:
    structs: List[SM64SaveStruct]
    fields: List[SM64SaveField]
    flags: List[SM64SaveFlag]


def _align_up(offset: int, align: int) -> int:
    return (offset + align - 1) // align * align if align else offset


def _select_us_lines(text: str) -> List[str]:
    """Keep only the lines active in the default (US/JP) build.

    The save structs put the EU-only ``language`` field and an alternate
    ``SUBTRAHEND`` behind ``#ifdef VERSION_EU``; selecting the branch where the
    regional version macros are undefined yields the common 0x200 EEPROM layout.
    Unknown conditionals (include guards, anything version-independent) are kept.
    """
    out: List[str] = []
    # Stack of (active_here, a_branch_was_taken) for each open #if.
    stack: List[Tuple[bool, bool]] = []

    def parent_active() -> bool:
        return all(a for a, _ in stack)

    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith("#ifdef"):
            cond = s[len("#ifdef") :].strip() not in _FALSE_MACROS
            stack.append((parent_active() and cond, cond))
        elif s.startswith("#ifndef"):
            # Include guards / unknown macros: keep the contents.
            stack.append((parent_active(), True))
        elif s.startswith("#if"):
            cond = not any(m in s for m in _FALSE_MACROS)
            stack.append((parent_active() and cond, cond))
        elif s.startswith("#elif"):
            if stack:
                _, taken = stack[-1]
                top = stack.pop()
                cond = (not any(m in s for m in _FALSE_MACROS)) and not taken
                stack.append((parent_active() and cond, taken or cond))
                del top
        elif s.startswith("#else"):
            if stack:
                _, taken = stack[-1]
                stack.pop()
                stack.append((parent_active() and not taken, True))
        elif s.startswith("#endif"):
            if stack:
                stack.pop()
        elif parent_active():
            out.append(raw)
    return out


def _clean_comment(line: str) -> str:
    text = line.lstrip("/").lstrip("*").strip()
    return text.rstrip("/").rstrip("*").strip()


def _doc_above(lines: List[str], idx: int) -> Optional[str]:
    """Return the contiguous comment block immediately above ``lines[idx]``."""
    collected: List[str] = []
    j = idx - 1
    while j >= 0:
        stripped = lines[j].strip()
        if stripped == "":
            break
        is_comment = (
            stripped.startswith("//")
            or stripped.startswith("/*")
            or stripped.startswith("*")
            or stripped.endswith("*/")
        )
        if not is_comment:
            break
        collected.append(stripped)
        if stripped.startswith("/*"):
            break
        j -= 1
    cleaned = [c for c in (_clean_comment(s) for s in reversed(collected)) if c]
    joined = " ".join(cleaned).strip()
    return joined or None


def _typedef_sizes(text: str) -> Dict[str, Tuple[int, int]]:
    """Resolve ``typedef <primitive> Name[...];`` aliases to (size, align).

    e.g. ``typedef s16 Vec3s[3];`` -> ``Vec3s = (6, 2)``. Aliases whose base is
    not a known primitive are skipped (none are needed by the save structs).
    """
    sizes: Dict[str, Tuple[int, int]] = {}
    for raw in text.splitlines():
        m = _TYPEDEF_RE.match(raw.strip())
        if not m or m.group("base") not in PRIMITIVES:
            continue
        base_size, base_align = PRIMITIVES[m.group("base")]
        count = 1
        for dim in re.findall(r"\[(\d+)\]", m.group("arr")):
            count *= int(dim)
        sizes[m.group("name")] = (base_size * count, base_align)
    return sizes


def _course_counts(repo: Path) -> Dict[str, int]:
    """Resolve COURSE_COUNT / COURSE_STAGES_COUNT from levels/course_defines.h.

    The enum (in course_table.h) numbers ``COURSE_NONE`` 0 then the main
    ``DEFINE_COURSE`` courses, so ``COURSE_STAGES_COUNT`` is the main count minus
    that sentinel; ``COURSE_COUNT`` adds the ``DEFINE_BONUS_COURSE`` entries.
    """
    path = repo.joinpath(*COURSE_DEFINES)
    if not path.is_file():
        return {}
    n_main = n_bonus = 0
    for line in path.read_text().splitlines():
        if extract_macro_args(line, "DEFINE_BONUS_COURSE") is not None:
            n_bonus += 1
        elif extract_macro_args(line, "DEFINE_COURSE") is not None:
            n_main += 1
    if not n_main:
        return {}
    stages = n_main - 1  # COURSE_NONE is the first DEFINE_COURSE (index 0)
    return {"COURSE_STAGES_COUNT": stages, "COURSE_COUNT": stages + n_bonus}


def _parse_structs(lines: List[str]) -> Dict[str, Dict[str, object]]:
    """Parse every ``struct NAME { ... };`` into its doc and member list.

    Each member is ``(name, base_type, dim_exprs, doc)`` where ``dim_exprs`` are
    the raw text of each ``[...]`` subscript (evaluated later, once the constants
    and earlier struct sizes they may reference are known).
    """
    structs: Dict[str, Dict[str, object]] = {}
    i = 0
    while i < len(lines):
        match = _STRUCT_START.match(lines[i].strip())
        if not match:
            i += 1
            continue
        name = match.group(1)
        doc = _doc_above(lines, i)
        members: List[Tuple[str, str, List[str], Optional[str]]] = []
        pending: List[str] = []
        depth = 1
        j = i + 1
        while j < len(lines) and depth > 0:
            raw = lines[j]
            stripped = raw.strip()
            depth += raw.count("{") - raw.count("}")
            if depth <= 0:
                break
            if (
                stripped.startswith("//")
                or stripped.startswith("/*")
                or stripped.startswith("*")
            ):
                cleaned = _clean_comment(stripped)
                if cleaned:
                    pending.append(cleaned)
                j += 1
                continue
            if stripped == "":
                pending = []
                j += 1
                continue
            member = _MEMBER_RE.match(strip_comments(stripped))
            if member:
                dims = re.findall(r"\[([^\]]*)\]", member.group("dims"))
                members.append(
                    (
                        member.group("name"),
                        member.group("type"),
                        dims,
                        " ".join(pending) or None,
                    )
                )
            pending = []
            j += 1
        structs[name] = {"doc": doc, "members": members}
        i = j + 1
    return structs


def _eval_dim(expr: str, symbols: Dict[str, int]) -> int:
    """Evaluate one array-dimension expression to an integer.

    Rewrites ``sizeof(struct X)`` to a ``__sizeof_X`` symbol (seeded as each
    struct is sized) so the EEPROM padding expression, which is written in terms
    of ``sizeof(struct SaveFile)``, reduces like any other constant expression.
    """
    rewritten = re.sub(r"sizeof\s*\(\s*struct\s+(\w+)\s*\)", r"__sizeof_\1", expr)
    rewritten = re.sub(r"sizeof\s*\(\s*(\w+)\s*\)", r"__sizeof_\1", rewritten)
    value = evaluate_int(rewritten, symbols)
    if value is None:
        raise ValueError(f"Cannot evaluate array dimension: {expr!r}")
    return value


def _parse_flags(define_map: Dict[str, int]) -> List[SM64SaveFlag]:
    """Decode the ``SAVE_FLAG_*`` single-bit ``#define``s into per-bit rows."""
    flags: List[SM64SaveFlag] = []
    for name, value in define_map.items():
        if not name.startswith("SAVE_FLAG_"):
            continue
        if value <= 0 or (value & (value - 1)) != 0:
            continue  # not a single bit -- the conversion macros, etc.
        flags.append(
            SM64SaveFlag(
                flag_group="flags",
                bit=value.bit_length() - 1,
                flag_name=name,
                mask=value,
            )
        )
    flags.sort(key=lambda f: f.bit)
    return flags


def parse_save_layout(repo: Path) -> ParsedSaveLayout:
    """Compute the byte layout of the EEPROM save buffer from save_file.h.

    The header's structs are parsed and sized under the N64 ABI; only those
    reachable from ``SaveBuffer`` (the EEPROM image) are emitted, plus the
    bit decode of the ``flags`` word. The computed ``SaveBuffer`` size is exactly
    ``EEPROM_SIZE`` -- callers/tests assert that as the completeness check.
    """
    save_h = repo.joinpath(*SAVE_FILE_H)
    if not save_h.is_file():
        return ParsedSaveLayout([], [], [])
    us_lines = _select_us_lines(save_h.read_text())

    define_map: Dict[str, int] = {}
    for key, value in parse_c_defines("\n".join(us_lines)):
        define_map[key] = value  # later definition wins (the US #else branch)
    symbols: Dict[str, int] = dict(define_map)
    symbols.update(_course_counts(repo))

    type_sizes = dict(PRIMITIVES)
    types_h = repo.joinpath(*TYPES_H)
    if types_h.is_file():
        type_sizes.update(_typedef_sizes(types_h.read_text()))

    structs = _parse_structs(us_lines)
    if EEPROM_ROOT not in structs:
        return ParsedSaveLayout([], [], [])

    struct_names = set(structs)
    computed: Dict[str, Tuple[int, int]] = {}
    fields_out: Dict[str, List[SM64SaveField]] = {}

    def compute(name: str) -> Tuple[int, int]:
        if name in computed:
            return computed[name]
        members = structs[name]["members"]
        assert isinstance(members, list)
        offset = 0
        align_max = 1
        emitted: List[SM64SaveField] = []
        for seq, (field_name, base_type, dim_exprs, doc) in enumerate(members):
            if base_type in struct_names:
                elem_size, elem_align = compute(base_type)
            elif base_type in type_sizes:
                elem_size, elem_align = type_sizes[base_type]
            else:
                raise ValueError(f"Unknown type {base_type!r} in struct {name}")
            dim_vals = [_eval_dim(expr, symbols) for expr in dim_exprs]
            count = 1
            for dim in dim_vals:
                count *= dim
            offset = _align_up(offset, elem_align)
            total = elem_size * count
            emitted.append(
                SM64SaveField(
                    struct_name=name,
                    seq=seq,
                    field_name=field_name,
                    type_name=base_type,
                    dims=",".join(str(d) for d in dim_vals),
                    count=count,
                    elem_size=elem_size,
                    offset=offset,
                    size=total,
                    is_struct=base_type in struct_names,
                    doc=doc,
                )
            )
            offset += total
            align_max = max(align_max, elem_align)
        size = _align_up(offset, align_max)
        computed[name] = (size, align_max)
        type_sizes[name] = (size, align_max)
        symbols[f"__sizeof_{name}"] = size
        fields_out[name] = emitted
        return computed[name]

    compute(EEPROM_ROOT)

    structs_out = [
        SM64SaveStruct(
            struct_name=name,
            size=computed[name][0],
            align=computed[name][1],
            doc=structs[name]["doc"],  # type: ignore[arg-type]
        )
        for name in computed
    ]
    fields = [field for name in computed for field in fields_out[name]]
    return ParsedSaveLayout(structs_out, fields, _parse_flags(define_map))
