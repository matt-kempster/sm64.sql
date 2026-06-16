from typing import List, Optional


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
