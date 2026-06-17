"""Parse the in-game course and star names from text/<lang>/courses.h.

The file lists, per course, the file-select course name and its star names via
multi-line macros::

    COURSE_ACTS(COURSE_BOB, _(" 1 BOB-OMB BATTLEFIELD"),
        _("BIG BOB-OMB ON THE SUMMIT"), _("FOOTRACE WITH KOOPA THE QUICK"), ...)
    SECRET_STAR(COURSE_BITDW, _("   BOWSER IN THE DARK WORLD"))

``COURSE_ACTS`` gives a main course's name plus its six act/star names;
``SECRET_STAR`` gives a bonus course whose single star name doubles as the
course name. The leading ``_(...)`` is the game's charmap macro; the text is
plain ASCII (with leading spaces used to align the course number in-game).

Two tables come out of this:

* ``course_name`` -- the file-select name of each course (``number`` is the 1-15
  course number, 0 for a bonus/secret course), joining ``course`` by name.
* ``star`` -- every named star (``kind`` is ``main`` for the six acts, ``secret``
  for a bonus-course star), also joining ``course`` by name.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

from sm64_sql.parse_utils import extract_macro_args, resolve_c_string, strip_comments


@dataclass
class SM64CourseName:
    course_name: str  # the COURSE_* enum, joins to course.course_name
    number: int  # in-game course number (1-15), or 0 for a bonus/secret course
    name: str  # the file-select course name, e.g. "BOB-OMB BATTLEFIELD"


@dataclass
class SM64Star:
    course_name: str  # the COURSE_* enum, joins to course.course_name
    kind: str  # "main" (one of the six acts) or "secret" (a bonus-course star)
    act: int  # 1-6 for a main-course star, 0 for a secret-course star
    name: str  # the star name, e.g. "WATCH FOR ROLLING ROCKS"


def _macro_calls(text: str, macro_name: str) -> List[List[str]]:
    """Return the argument lists of every ``macro_name(...)`` call in ``text``.

    Calls may span several lines; extract_macro_args walks balanced parens, and
    the per-name boundary check stops SECRET_STAR matching CASTLE_SECRET_STARS.
    """
    calls: List[List[str]] = []
    search = 0
    while True:
        index = text.find(macro_name, search)
        if index == -1:
            return calls
        args = extract_macro_args(text[index:], macro_name)
        if args is not None:
            calls.append(args)
        search = index + len(macro_name)


def _split_number(name: str) -> Tuple[int, str]:
    """Split a leading course number off a name (" 1 BOB-OMB..." -> (1, "BOB...."))."""
    name = name.strip()
    head, _sep, rest = name.partition(" ")
    if head.isdigit():
        return int(head), rest.strip()
    return 0, name


def parse_course_text(
    courses_path: Path,
) -> Tuple[List[SM64CourseName], List[SM64Star]]:
    # strip_comments is line-oriented, so apply it per line before rejoining.
    text = "\n".join(
        strip_comments(line) for line in courses_path.read_text().splitlines()
    )
    course_names: List[SM64CourseName] = []
    stars: List[SM64Star] = []

    for args in _macro_calls(text, "COURSE_ACTS"):
        if len(args) != 8:
            raise ValueError(f"Expected 8 COURSE_ACTS args, got {len(args)}: {args}")
        course = args[0].strip()
        number, name = _split_number(resolve_c_string(args[1], {}))
        course_names.append(SM64CourseName(course, number, name))
        for act, star_arg in enumerate(args[2:], start=1):
            star_name = resolve_c_string(star_arg, {}).strip()
            if star_name:
                stars.append(SM64Star(course, "main", act, star_name))

    for args in _macro_calls(text, "SECRET_STAR"):
        if len(args) != 2:
            raise ValueError(f"Expected 2 SECRET_STAR args, got {len(args)}: {args}")
        course = args[0].strip()
        name = resolve_c_string(args[1], {}).strip()
        if not name:
            continue  # the COURSE_CAKE_END sentinel carries an empty name
        course_names.append(SM64CourseName(course, 0, name))
        stars.append(SM64Star(course, "secret", 0, name))

    return course_names, stars
