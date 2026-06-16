from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64Area:
    level: str  # level folder
    area: int  # AREA index
    geo: str  # geo layout symbol (the AREA's second argument)
    terrain_type: str  # TERRAIN_TYPE value (e.g. TERRAIN_GRASS), or ""
    background_music: str  # SET_BACKGROUND_MUSIC seq (joins sequence.seq_name), or ""
    dialog: str  # SHOW_DIALOG dialog id (joins dialog.dialog_name), or ""


def parse_areas(path: Path, level: str) -> List[SM64Area]:
    """Parse AREA blocks from a level script.c with their terrain/music/dialog."""
    areas: List[SM64Area] = []
    current: Optional[SM64Area] = None
    for line in path.read_text().splitlines():
        line = line.strip()

        area_args = extract_macro_args(line, "AREA")
        if area_args is not None:
            try:
                index = int(area_args[0])
            except ValueError:
                index = 0
            geo = area_args[1] if len(area_args) > 1 else ""
            current = SM64Area(
                level=level,
                area=index,
                geo=geo,
                terrain_type="",
                background_music="",
                dialog="",
            )
            continue
        if line.startswith("END_AREA"):
            if current is not None:
                areas.append(current)
                current = None
            continue
        if current is None:
            continue

        terrain = extract_macro_args(line, "TERRAIN_TYPE")
        if terrain:
            current.terrain_type = terrain[0]
            continue
        music = extract_macro_args(line, "SET_BACKGROUND_MUSIC")
        if music is not None and len(music) >= 2:
            current.background_music = music[1]
            continue
        dialog = extract_macro_args(line, "SHOW_DIALOG")
        if dialog is not None and len(dialog) >= 2:
            current.dialog = dialog[1]
            continue
    return areas
