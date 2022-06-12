from asyncore import write
from dataclasses import dataclass
from pathlib import Path
from typing import List

from model import SM64Model, parse_model_ids
from object import SM64Object, try_parse_object


@dataclass
class SM64Everything:
    sm64_objects: List[SM64Object]
    sm64_models: List[SM64Model]


def parse_level(path: Path) -> List[SM64Object]:
    script = (path / "script.c").read_text().splitlines()
    level_name = path.name
    sm64_objects = []
    for line in script:
        line = line.strip()
        if sm64_object := try_parse_object(line, level_name):
            sm64_objects.append(sm64_object)
    return sm64_objects


def parse_repo(repo: Path) -> SM64Everything:
    sm64_objects = []
    for level_dir in (repo / "levels").iterdir():
        if level_dir.is_dir():
            sm64_objects_level = parse_level(level_dir)
            sm64_objects.extend(sm64_objects_level)
    model_ids_file = repo / "include" / "model_ids.h"
    sm64_models = parse_model_ids(model_ids_file)
    return SM64Everything(sm64_objects, sm64_models)
