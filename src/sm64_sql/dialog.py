from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List

from sm64_sql.parse_utils import parse_c_enum


@dataclass
class SM64Dialog:
    dialog_name: str  # the DIALOG_* enum, e.g. DIALOG_000
    dialog_id: int  # numeric id from enum DialogID
    lines_per_box: int
    left_offset: int
    width: int
    text: str  # resolved dialog text (newlines preserved)


def _unescape_c_string_body(body: str) -> str:
    """Turn the inside of a C string literal into its actual characters.

    Handles ``\\n`` / ``\\t`` escapes, escaped quotes/backslashes, and
    ``\\``-at-end-of-line continuations (which join with no separator).
    """
    out: List[str] = []
    i = 0
    while i < len(body):
        char = body[i]
        if char == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "\n":
                pass  # line continuation: join with nothing
            else:
                out.append(nxt)  # \" \\ and anything else: take literally
            i += 2
        else:
            out.append(char)
            i += 1
    return "".join(out)


def _resolve_c_string(expr: str, defines: Dict[str, str]) -> str:
    """Resolve a C string expression: adjacent literals and macro names joined.

    e.g. ``"his " COMRADES " in other"`` with COMRADES -> "comrades".
    Unknown macros resolve to an empty string.
    """
    parts: List[str] = []
    i = 0
    while i < len(expr):
        char = expr[i]
        if char == '"':
            i += 1
            start = i
            while i < len(expr):
                if expr[i] == "\\":
                    i += 2
                    continue
                if expr[i] == '"':
                    break
                i += 1
            parts.append(_unescape_c_string_body(expr[start:i]))
            i += 1  # skip closing quote
        elif char.isalpha() or char == "_":
            start = i
            while i < len(expr) and (expr[i].isalnum() or expr[i] == "_"):
                i += 1
            parts.append(defines.get(expr[start:i], ""))
        else:
            i += 1  # whitespace / newlines between tokens
    return "".join(parts)


def _parse_string_defines(text: str) -> Dict[str, str]:
    """Map ``#define NAME "value"`` entries to their resolved string value.

    Later definitions win, so for the EU/else pairs in dialogs.h the non-EU
    (default) values — which come second — take precedence.
    """
    defines: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("#define "):
            continue
        rest = line[len("#define ") :].strip()
        name, sep, value = rest.partition(" ")
        value = value.strip()
        if sep and value.startswith('"'):
            defines[name] = _resolve_c_string(value, defines)
    return defines


def _iter_define_dialog_blocks(text: str) -> Iterator[str]:
    """Yield the argument text of each DEFINE_DIALOG(...) call (quote-aware)."""
    marker = "DEFINE_DIALOG"
    search = 0
    while True:
        pos = text.find(marker, search)
        if pos == -1:
            return
        open_paren = text.find("(", pos)
        if open_paren == -1:
            return
        i = open_paren + 1
        start = i
        depth = 1
        in_string = False
        while i < len(text) and depth > 0:
            char = text[i]
            if in_string:
                if char == "\\":
                    i += 2
                    continue
                if char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield text[start:i]
        search = i + 1


def parse_dialogs(dialogs_path: Path, dialog_ids_path: Path) -> List[SM64Dialog]:
    """Parse dialog text (text/<lang>/dialogs.h) keyed by enum DialogID ids."""
    ids = dict(parse_c_enum(dialog_ids_path.read_text(), "DialogID"))
    text = dialogs_path.read_text()
    defines = _parse_string_defines(text)

    dialogs = []
    for block in _iter_define_dialog_blocks(text):
        text_start = block.find("_(")
        if text_start == -1:
            continue
        meta = [arg.strip() for arg in block[:text_start].split(",") if arg.strip()]
        if len(meta) < 5:
            raise ValueError(f"Unexpected DEFINE_DIALOG arguments: {meta}")
        text_expr = block[text_start + 2 :].rstrip()
        if text_expr.endswith(")"):
            text_expr = text_expr[:-1]
        dialog_name = meta[0]
        dialogs.append(
            SM64Dialog(
                dialog_name=dialog_name,
                dialog_id=ids.get(dialog_name, -1),
                lines_per_box=int(meta[2]),
                left_offset=int(meta[3]),
                width=int(meta[4]),
                text=_resolve_c_string(text_expr, defines),
            )
        )
    return dialogs
