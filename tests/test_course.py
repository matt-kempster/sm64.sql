from sm64_sql.course import parse_courses

COURSE_DEFINES_H = """\
/* a block comment describing the fields */
DEFINE_COURSE(COURSE_NONE, 0x44444440)            // (0)  Course Hub (Castle Grounds)
DEFINE_COURSE(COURSE_BOB,  0x00022240)            // (1)  Bob-omb Battlefield
DEFINE_COURSE(COURSE_WF,   0x00002040)            // (2)  Whomp's Fortress
DEFINE_COURSES_END()
DEFINE_BONUS_COURSE(COURSE_PSS, 0x24444440) // (19) The Princess's Secret Slide
"""


def test_parse_courses(tmp_path):
    path = tmp_path / "course_defines.h"
    path.write_text(COURSE_DEFINES_H)
    courses = parse_courses(path)
    by_name = {c.course_name: c for c in courses}

    # DEFINE_COURSES_END() is not a course and must be skipped.
    assert len(courses) == 4

    bob = by_name["COURSE_BOB"]
    assert bob.display_name == "Bob-omb Battlefield"
    assert bob.dance_cutscene == 0x00022240
    assert bob.is_bonus is False

    # A display name containing parentheses is captured whole.
    assert by_name["COURSE_NONE"].display_name == "Course Hub (Castle Grounds)"
    # Apostrophes survive.
    assert by_name["COURSE_WF"].display_name == "Whomp's Fortress"
    # Bonus courses are flagged.
    assert by_name["COURSE_PSS"].is_bonus is True
