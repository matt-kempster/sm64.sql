from sm64_sql.sequence import parse_sequences

SEQ_IDS_H = """\
#ifndef SEQ_IDS_H
#define SEQ_IDS_H

#define SEQ_BASE_ID 0x7f
#define SEQ_VARIATION 0x80

enum SeqId {
    SEQ_SOUND_PLAYER,                 // 0x00
    SEQ_EVENT_CUTSCENE_COLLECT_STAR,  // 0x01
    SEQ_MENU_TITLE_SCREEN,            // 0x02
    SEQ_LEVEL_GRASS,                  // 0x03
    SEQ_COUNT
};

#endif
"""


def test_parse_sequences(tmp_path):
    path = tmp_path / "seq_ids.h"
    path.write_text(SEQ_IDS_H)
    seqs = parse_sequences(path)
    by_name = {s.seq_name: s.seq_id for s in seqs}

    # The SEQ_COUNT sentinel is excluded; the #define lines are not enum members.
    assert "SEQ_COUNT" not in by_name
    assert "SEQ_BASE_ID" not in by_name
    assert len(seqs) == 4

    # Values auto-increment from zero.
    assert by_name["SEQ_SOUND_PLAYER"] == 0x00
    assert by_name["SEQ_LEVEL_GRASS"] == 0x03
