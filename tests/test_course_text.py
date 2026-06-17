from sm64_sql.course_text import parse_course_text

COURSES_H = """\
COURSE_ACTS(COURSE_BOB, _(" 1 BOB-OMB BATTLEFIELD"),
       _("BIG BOB-OMB ON THE SUMMIT")     , _("FOOTRACE WITH KOOPA THE QUICK") , _("SHOOT TO THE ISLAND IN THE SKY"),
       _("FIND THE 8 RED COINS")          , _("MARIO WINGS TO THE SKY")        , _("BEHIND CHAIN CHOMP'S GATE"))

COURSE_ACTS(COURSE_CCM, _(" 4 COOL, COOL MOUNTAIN"),
       _("SLIP SLIDIN' AWAY")             , _("LI'L PENGUIN LOST")             , _("BIG PENGUIN RACE"),
       _("FROSTY SLIDE FOR 8 RED COINS")  , _("SNOWMAN'S LOST HIS HEAD")       , _("WALL KICKS WILL WORK"))

SECRET_STAR(COURSE_BITDW, _("   BOWSER IN THE DARK WORLD"))
SECRET_STAR(COURSE_CAKE_END, _(""))

CASTLE_SECRET_STARS(_("   CASTLE SECRET STARS"))

EXTRA_TEXT(0, _("ONE OF THE CASTLE'S SECRET STARS!"))
"""


def _parse(tmp_path):
    path = tmp_path / "courses.h"
    path.write_text(COURSES_H)
    return parse_course_text(path)


def test_course_names(tmp_path):
    course_names, _ = _parse(tmp_path)
    by_course = {c.course_name: c for c in course_names}
    # Main courses get their number split off the file-select name.
    assert by_course["COURSE_BOB"].number == 1
    assert by_course["COURSE_BOB"].name == "BOB-OMB BATTLEFIELD"
    # A name containing a comma (inside the _() parens) stays intact.
    assert by_course["COURSE_CCM"].number == 4
    assert by_course["COURSE_CCM"].name == "COOL, COOL MOUNTAIN"
    # A secret course has no number; its name doubles as the star name.
    assert by_course["COURSE_BITDW"].number == 0
    assert by_course["COURSE_BITDW"].name == "BOWSER IN THE DARK WORLD"
    # The empty CAKE_END sentinel is skipped.
    assert "COURSE_CAKE_END" not in by_course


def test_stars(tmp_path):
    _, stars = _parse(tmp_path)
    bob = [s for s in stars if s.course_name == "COURSE_BOB"]
    # Six acts, numbered 1-6, in order.
    assert [s.act for s in bob] == [1, 2, 3, 4, 5, 6]
    assert all(s.kind == "main" for s in bob)
    assert bob[0].name == "BIG BOB-OMB ON THE SUMMIT"
    assert bob[5].name == "BEHIND CHAIN CHOMP'S GATE"  # apostrophe preserved

    # The secret course contributes one star (kind=secret, act=0).
    secret = [s for s in stars if s.course_name == "COURSE_BITDW"]
    assert secret == [secret[0]] and secret[0].kind == "secret" and secret[0].act == 0
    assert secret[0].name == "BOWSER IN THE DARK WORLD"


def test_castle_secret_and_extra_text_are_ignored(tmp_path):
    course_names, stars = _parse(tmp_path)
    # CASTLE_SECRET_STARS / EXTRA_TEXT are UI labels, not courses or stars.
    names = {c.name for c in course_names} | {s.name for s in stars}
    assert "CASTLE SECRET STARS" not in names
    assert "ONE OF THE CASTLE'S SECRET STARS!" not in names
