import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

from sm64_sql.parse_utils import extract_macro_args

# Each sound define carries its precomputed value in a /* 0x........ */ comment.
_SOUND_VALUE = re.compile(r"/\*\s*(0x[0-9A-Fa-f]+)\s*\*/")


@dataclass
class SM64Sound:
    sound_name: str  # the SOUND_* define, e.g. SOUND_ACTION_TERRAIN_JUMP
    sound_id: int  # precomputed encoded value from the define's comment
    bank: str  # SOUND_BANK_* category (first SOUND_ARG_LOAD argument)


def parse_sounds(path: Path) -> List[SM64Sound]:
    """Parse the SOUND_* effect defines from include/sounds.h.

    Only defines built with SOUND_ARG_LOAD(...) and carrying a /* 0x.. */ value
    comment are real sound effects; bank/flag/helper defines are skipped. The
    bitfield value is read straight from the comment rather than recomputed.
    """
    sounds = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line.startswith("#define SOUND_") or "SOUND_ARG_LOAD(" not in line:
            continue
        value_match = _SOUND_VALUE.search(line)
        if value_match is None:
            continue  # excludes the SOUND_ARG_LOAD helper macro itself
        sound_name = line.split()[1]
        args = extract_macro_args(
            line[line.index("SOUND_ARG_LOAD") :], "SOUND_ARG_LOAD"
        )
        bank = args[0] if args else ""
        sounds.append(
            SM64Sound(
                sound_name=sound_name,
                sound_id=int(value_match.group(1), 16),
                bank=bank,
            )
        )
    return sounds
