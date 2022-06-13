from asyncore import write
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from macro_object import SM64MacroObject, try_parse_macro_object

from model import SM64Model, parse_model_ids
from object import SM64Object, try_parse_object


@dataclass
class SM64Everything:
    sm64_objects: List[SM64Object]
    sm64_macro_objects: List[SM64MacroObject]
    sm64_models: List[SM64Model]


def parse_levelscript(path: Path) -> List[SM64Object]:
    script = path.read_text().splitlines()
    level_name = path.name
    sm64_objects = []
    for line in script:
        line = line.strip()
        if sm64_object := try_parse_object(line, level_name):
            sm64_objects.append(sm64_object)
    return sm64_objects


def parse_macro_file(path: Path, level_name: str) -> List[SM64MacroObject]:
    script = path.read_text().splitlines()
    # TODO: figure out what to do with areas in the path
    sm64_macro_objects = []
    for line in script:
        line = line.strip()
        if sm64_macro_object := try_parse_macro_object(line, level_name):
            sm64_macro_objects.append(sm64_macro_object)
    return sm64_macro_objects


def parse_level(path: Path) -> Tuple[List[SM64Object], List[SM64MacroObject]]:
    sm64_objects = parse_levelscript(path / "script.c")
    macro_files = path.glob("**/macro.inc.c")
    sm64_macro_objects = []
    for macro_file in macro_files:
        sm64_macro_objects.extend(parse_macro_file(macro_file, path.name))
    return sm64_objects, sm64_macro_objects


def parse_repo(repo: Path) -> SM64Everything:
    sm64_objects = []
    sm64_macro_objects = []
    for level_dir in (repo / "levels").iterdir():
        if level_dir.is_dir():
            sm64_objects_level = parse_level(level_dir)
            sm64_objects.extend(sm64_objects_level[0])
            sm64_macro_objects.extend(sm64_objects_level[1])
    model_ids_file = repo / "include" / "model_ids.h"
    sm64_models = parse_model_ids(model_ids_file)
    return SM64Everything(sm64_objects, sm64_macro_objects, sm64_models)
