from typing import Dict, List, Optional, Tuple


def strip_block_comments(line: str) -> str:
    """Remove all ``/* ... */`` block comments from a single line."""
    while True:
        comment_start = line.find("/*")
        comment_end = line.find("*/")
        if comment_start == -1 or comment_end == -1:
            break
        line = line[:comment_start] + line[comment_end + 2 :]
    return line


def strip_comments_and_whitespace(line: str) -> str:
    """Remove block comments and surrounding whitespace from a single line."""
    return strip_block_comments(line).strip()


def strip_comments(line: str) -> str:
    """Remove block comments, a trailing ``//`` line comment, and whitespace."""
    return strip_block_comments(line).split("//")[0].strip()


def split_top_level(text: str, separator: str = ",") -> List[str]:
    """Split ``text`` on ``separator``, ignoring separators nested in brackets.

    SM64 macro arguments can themselves contain parenthesised expressions such
    as ``BPARAM2(41)`` or ``BPARAM1(0) | BPARAM2(1)``. A naive ``str.split(",")``
    would mishandle any argument that contained a comma inside its brackets, so
    only commas at bracket depth zero count as argument separators.
    """
    parts: List[str] = []
    depth = 0
    current = ""
    openers = "([{"
    closers = ")]}"
    for char in text:
        if char in openers:
            depth += 1
        elif char in closers:
            depth = max(0, depth - 1)
        if char == separator and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts


def _eval_enum_value(expr: str, seen: Dict[str, int]) -> int:
    expr = expr.strip()
    try:
        # int(expr, 0) understands decimal, 0x hex, and a leading minus sign.
        return int(expr, 0)
    except ValueError:
        pass
    if expr in seen:
        return seen[expr]
    raise ValueError(f"Cannot evaluate enum value: {expr!r}")


def parse_c_enum(text: str, enum_name: str) -> List[Tuple[str, int]]:
    """Parse ``enum <enum_name> { ... }`` into ``(name, value)`` pairs.

    Values auto-increment from 0 like C enums do, honouring explicit ``= N``
    assignments (decimal, hex, negative, or a reference to an earlier
    enumerator). Sentinel entries such as a trailing ``*_COUNT`` are returned
    too; callers filter what they do not want.
    """
    entries: List[Tuple[str, int]] = []
    seen: Dict[str, int] = {}
    within = False
    value = 0
    for raw in text.splitlines():
        line = strip_block_comments(raw).split("//")[0].strip()
        if not within:
            rest = (
                line[len("enum " + enum_name) :]
                if line.startswith("enum " + enum_name)
                else None
            )
            if rest is not None and (rest == "" or rest[0] in " \t{"):
                within = True
            continue
        if line.startswith("}"):
            break
        for token in line.split(","):
            token = token.strip()
            if not token:
                continue
            if "=" in token:
                name, _, expr = token.partition("=")
                name = name.strip()
                value = _eval_enum_value(expr, seen)
            else:
                name = token
            if not name.isidentifier():
                continue
            entries.append((name, value))
            seen[name] = value
            value += 1
    return entries


def unescape_c_string_body(body: str) -> str:
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


def resolve_c_string(expr: str, defines: Dict[str, str]) -> str:
    """Resolve a C string expression: adjacent literals and macro names joined.

    e.g. ``"his " COMRADES " in other"`` with COMRADES -> "comrades".
    Unknown macros resolve to an empty string. A bare ``_("...")`` wrapper
    resolves to just the string, since ``_`` is an unknown macro.
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
            parts.append(unescape_c_string_body(expr[start:i]))
            i += 1  # skip closing quote
        elif char.isalpha() or char == "_":
            start = i
            while i < len(expr) and (expr[i].isalnum() or expr[i] == "_"):
                i += 1
            parts.append(defines.get(expr[start:i], ""))
        else:
            i += 1  # whitespace / newlines / parens between tokens
    return "".join(parts)


def extract_macro_args(line: str, macro_name: str) -> Optional[List[str]]:
    """Return the comment-stripped arguments of ``macro_name(...)`` in ``line``.

    Returns ``None`` if the line does not begin with a call to exactly
    ``macro_name`` (so ``OBJECT`` does not match ``OBJECT_WITH_ACTS``). The
    arguments are split on top-level commas and individually stripped of block
    comments and whitespace.

    The decomp aligns columns by padding the macro name with spaces before its
    ``(`` (e.g. ``MACRO_OBJECT               (...)``), so whitespace between the
    name and the opening paren is allowed.
    """
    line = line.strip()
    if not line.startswith(macro_name):
        return None
    start = len(macro_name)
    while start < len(line) and line[start] in " \t":
        start += 1
    # The next non-space character must be the opening paren; this is what keeps
    # ``OBJECT`` from matching ``OBJECT_WITH_ACTS`` (whose next char is ``_``).
    if start >= len(line) or line[start] != "(":
        return None

    # Walk from the opening paren to its matching close paren so that trailing
    # tokens (e.g. a stray comma or comment) outside the call are ignored.
    depth = 0
    end = -1
    for index in range(start, len(line)):
        char = line[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end == -1:
        return None

    inner = strip_block_comments(line[start + 1 : end])
    return [part.strip() for part in split_top_level(inner, ",")]
