"""End-to-end parse against a real decomp checkout.

Set the SM64_DECOMP_PATH environment variable to the root of an
n64decomp/sm64 checkout to enable these tests; otherwise they are skipped.
"""

import os
from pathlib import Path

import pytest

from sm64_sql.everything import parse_repo

_decomp_env = os.environ.get("SM64_DECOMP_PATH")
_decomp = Path(_decomp_env) if _decomp_env else None

pytestmark = pytest.mark.skipif(
    _decomp is None or not (_decomp / "levels").is_dir(),
    reason="set SM64_DECOMP_PATH to a decomp checkout to run integration tests",
)


@pytest.fixture(scope="module")
def everything():
    assert _decomp is not None
    return parse_repo(_decomp)


def test_parse_repo_finds_entities(everything):
    # Every category should be populated for a real decomp.
    assert len(everything.sm64_objects) > 0
    assert len(everything.sm64_macro_objects) > 0
    assert len(everything.sm64_models) > 0
    assert len(everything.sm64_macro_presets) > 0
    assert len(everything.sm64_levels) > 0


def test_levels_have_folders_matching_object_levels(everything):
    folders = {lvl.folder for lvl in everything.sm64_levels if not lvl.is_stub}
    object_levels = {obj.level for obj in everything.sm64_objects}
    # The vast majority of placed-object "levels" are real level folders.
    assert "bbh" in folders
    assert object_levels & folders


def test_model_ids_are_unique_names(everything):
    names = [m.model_name for m in everything.sm64_models]
    assert len(names) == len(set(names))


def test_objects_reference_known_levels(everything):
    levels = {obj.level for obj in everything.sm64_objects}
    # A handful of well-known course folders that always exist.
    assert {"bob", "jrb"} <= levels
