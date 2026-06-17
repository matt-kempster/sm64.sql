"""Parse per-level model bindings from level scripts.

A level script binds a model id to a geo layout (or display list) with::

    LOAD_MODEL_FROM_GEO(MODEL_BOB_BUBBLY_TREE, bubbly_tree_geo)
    LOAD_MODEL_FROM_DL(model, displayList, layer)   # unused in vanilla

The same model *slot* is reused across levels — e.g. ``MODEL_LEVEL_GEOMETRY_03``
is bound to a different geo in BoB, CCM, Bowser 1, ... — so unlike the global
``model`` table (from model_ids.h) this binding is per level. The shared
``levels/scripts.c`` loads (Mario, common effects, ...) are recorded with the
level ``common``.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from sm64_sql.parse_utils import extract_macro_args


@dataclass
class SM64ModelLoad:
    level: str  # level folder, or "common" for the shared levels/scripts.c loads
    model_name: str  # MODEL_* (joins to model.model_name)
    geo: str  # the geo layout symbol bound to the slot (or display list for a DL load)
    layer: Optional[str]  # graph-node layer for a DL load; NULL for a geo load
    kind: str  # "geo" or "dl"


def try_parse_model_load(line: str, level: str) -> Optional[SM64ModelLoad]:
    geo_args = extract_macro_args(line, "LOAD_MODEL_FROM_GEO")
    if geo_args is not None:
        if len(geo_args) != 2:
            raise ValueError(f"Expected 2 LOAD_MODEL_FROM_GEO args: {line.strip()}")
        return SM64ModelLoad(level, geo_args[0], geo_args[1], None, "geo")

    dl_args = extract_macro_args(line, "LOAD_MODEL_FROM_DL")
    if dl_args is not None:
        if len(dl_args) != 3:
            raise ValueError(f"Expected 3 LOAD_MODEL_FROM_DL args: {line.strip()}")
        return SM64ModelLoad(level, dl_args[0], dl_args[1], dl_args[2], "dl")

    return None


def parse_model_loads(path: Path, level: str) -> List[SM64ModelLoad]:
    loads = []
    for line in path.read_text().splitlines():
        load = try_parse_model_load(line.strip(), level)
        if load is not None:
            loads.append(load)
    return loads
