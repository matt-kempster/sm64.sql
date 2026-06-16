from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List


@dataclass
class SM64Model:
    model_name: str
    model_id: int


def parse_model_ids(path: Path) -> List[SM64Model]:
    text = path.read_text().splitlines()
    models: List[SM64Model] = []
    # Some defines alias an earlier MODEL_* id (the level geometry overrides,
    # e.g. `#define MODEL_WF_GIANT_POLE MODEL_LEVEL_GEOMETRY_0D`). Keep a symbol
    # table so those resolve to a real id instead of silently reusing whatever
    # the previous iteration left in `model_id`.
    ids_by_name: Dict[str, int] = {}
    for line in text:
        line = line.strip()
        if not line.startswith("#define MODEL_"):
            continue
        parts = line.split()
        if len(parts) < 3:
            # e.g. the `#define MODEL_IDS_H` include guard, which has no value.
            continue
        model_name = parts[1]
        value = parts[2]
        if value.startswith("0x"):
            model_id = int(value, 16)
        elif value.isdigit():
            model_id = int(value)
        elif value in ids_by_name:
            model_id = ids_by_name[value]
        else:
            # An unresolved reference or expression; skip it rather than emit a
            # wrong id.
            continue
        ids_by_name[model_name] = model_id
        models.append(SM64Model(model_name, model_id))
    return models
