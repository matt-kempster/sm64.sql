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


def extract_macro_args(line: str, macro_name: str) -> Optional[List[str]]:
    """Return the comment-stripped arguments of ``macro_name(...)`` in ``line``.

    Returns ``None`` if the line does not begin with a call to exactly
    ``macro_name`` (so ``OBJECT`` does not match ``OBJECT_WITH_ACTS``). The
    arguments are split on top-level commas and individually stripped of block
    comments and whitespace.
    """
    line = line.strip()
    prefix = macro_name + "("
    if not line.startswith(prefix):
        return None

    # Walk from the opening paren to its matching close paren so that trailing
    # tokens (e.g. a stray comma or comment) outside the call are ignored.
    start = len(macro_name)
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
