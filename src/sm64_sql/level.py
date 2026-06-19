from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64Level:
    level_name: str  # the LEVEL_* enum, e.g. LEVEL_BBH
    course_name: str  # the COURSE_* enum, e.g. COURSE_BBH
    # the levels/<folder> name, joins to object.level etc. NULL for stub levels
    # (they have no folder); NULL keeps the column uniquely indexable so it can
    # be a foreign-key target.
    folder: Optional[str]
    internal_name: str  # the original ROM level name, e.g. "TERESA OBAKE"
    is_stub: bool  # STUB_LEVEL (no content) vs DEFINE_LEVEL


def parse_levels(path: Path) -> List[SM64Level]:
    """Parse the DEFINE_LEVEL / STUB_LEVEL X-macros in levels/level_defines.h.

    DEFINE_LEVEL(name, levelEnum, courseEnum, folder, ...) has a folder; the
    shorter STUB_LEVEL(name, levelEnum, courseEnum, ...) does not.
    """
    levels = []
    for line in path.read_text().splitlines():
        line = line.strip()
        for macro, is_stub in (("DEFINE_LEVEL", False), ("STUB_LEVEL", True)):
            args = extract_macro_args(line, macro)
            if args is None:
                continue
            minimum = 3 if is_stub else 4
            if len(args) < minimum:
                raise ValueError(f"Too few args in {macro}: {line}")
            levels.append(
                SM64Level(
                    level_name=args[1],
                    course_name=args[2],
                    folder=None if is_stub else args[3],
                    internal_name=args[0].strip('"'),
                    is_stub=is_stub,
                )
            )
            break
    return levels
