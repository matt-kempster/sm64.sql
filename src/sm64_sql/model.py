from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class SM64Model:
    model_name: str
    model_id: int
    # TODO: include level geo-overriding models


def parse_model_ids(path: Path) -> List[SM64Model]:
    text = path.read_text().splitlines()
    model_ids = []
    for line in text:
        line = line.strip()
        if not line.startswith("#define MODEL_"):
            continue
        parts = line.split()
        model_name = parts[1]
        try:
            model_id_str = parts[2]
        except IndexError:
            if line != "#define MODEL_IDS_H":
                print(f"Invalid line: {line}")
            continue
        if model_id_str.startswith("0x"):
            model_id = int(model_id_str, 16)
        elif model_id_str.isnumeric():
            model_id = int(model_id_str)
        else:
            # TODO: interpret model ids that reference other model ids
            pass
        model_ids.append(SM64Model(model_name, model_id))
    return model_ids
