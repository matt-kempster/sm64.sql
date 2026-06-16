from sm64_sql.dialog import parse_dialogs

DIALOG_IDS_H = """\
enum DialogID {
    DIALOG_NONE = -1,
    DIALOG_000,
    DIALOG_001,
    DIALOG_COUNT
};
"""

DIALOGS_H = """\
#ifdef VERSION_EU
#define COMRADES "friends"
#else
#define COMRADES "comrades"
#endif

DEFINE_DIALOG(DIALOG_000, 1, 6, 30, 200, _("\\
Hello, you and your\\n\\
" COMRADES "!"))

DEFINE_DIALOG(DIALOG_001, 1, 4, 95, 200, _("\\
Press [B] to talk."))
"""


def test_parse_dialogs(tmp_path):
    ids = tmp_path / "dialog_ids.h"
    dialogs = tmp_path / "dialogs.h"
    ids.write_text(DIALOG_IDS_H)
    dialogs.write_text(DIALOGS_H)

    parsed = parse_dialogs(dialogs, ids)
    by_name = {d.dialog_name: d for d in parsed}
    assert len(parsed) == 2

    d0 = by_name["DIALOG_000"]
    assert d0.dialog_id == 0
    assert d0.lines_per_box == 6
    assert d0.left_offset == 30
    assert d0.width == 200
    # Line continuations are joined, \n becomes a newline, and the macro is
    # resolved using the non-EU (default) value.
    assert d0.text == "Hello, you and your\ncomrades!"

    # Button glyphs stay as literal text.
    assert by_name["DIALOG_001"].text == "Press [B] to talk."
