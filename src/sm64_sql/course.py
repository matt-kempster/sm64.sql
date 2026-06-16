import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import extract_macro_args

# The human-readable name lives in a trailing comment like `// (5) Big Boo's
# Haunt`; capture everything after the `(index)` prefix (the name itself may
# contain parentheses, e.g. "Course Hub (Castle Grounds)").
_DISPLAY_NAME = re.compile(r"//\s*\(\d+\)\s*(.*?)\s*$")


@dataclass
class SM64Course:
    course_name: str  # the COURSE_* enum, e.g. COURSE_BOB (joins to level.course_name)
    display_name: str  # human-readable name, e.g. "Bob-omb Battlefield"
    dance_cutscene: int  # per-star dance cutscene bitmask
    is_bonus: bool  # DEFINE_BONUS_COURSE (caps/secret) vs a main DEFINE_COURSE


def parse_courses(path: Path) -> List[SM64Course]:
    """Parse DEFINE_COURSE / DEFINE_BONUS_COURSE in levels/course_defines.h."""
    courses = []
    for line in path.read_text().splitlines():
        line = line.strip()
        is_bonus = line.startswith("DEFINE_BONUS_COURSE")
        macro = "DEFINE_BONUS_COURSE" if is_bonus else "DEFINE_COURSE"
        args = extract_macro_args(line, macro)
        if args is None:
            continue
        if len(args) < 2:
            raise ValueError(f"Too few args in {macro}: {line}")
        name_match = _DISPLAY_NAME.search(line)
        courses.append(
            SM64Course(
                course_name=args[0],
                display_name=name_match.group(1) if name_match else "",
                dance_cutscene=int(args[1], 16),
                is_bonus=is_bonus,
            )
        )
    return courses
