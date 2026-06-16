from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import parse_c_enum


@dataclass
class SM64Sequence:
    seq_name: str  # the SEQ_* enum, e.g. SEQ_LEVEL_GRASS
    seq_id: int  # the sequence (music) id


def parse_sequences(path: Path) -> List[SM64Sequence]:
    """Parse the music sequence ids from the ``enum SeqId`` in seq_ids.h."""
    return [
        SM64Sequence(seq_name=name, seq_id=value)
        for name, value in parse_c_enum(path.read_text(), "SeqId")
        if name != "SEQ_COUNT"
    ]
