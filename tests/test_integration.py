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
    assert len(everything.sm64_courses) > 0
    assert len(everything.sm64_sequences) > 0
    assert len(everything.sm64_dialogs) > 0
    assert len(everything.sm64_special_presets) > 0
    assert len(everything.sm64_special_objects) > 0


def test_special_objects_reference_known_presets(everything):
    # Join by id (not name): some placements use enum aliases like
    # special_haunted_door that have no array row of their own.
    preset_ids = {p.preset_id for p in everything.sm64_special_presets}
    used = {o.preset_id for o in everything.sm64_special_objects}
    assert used <= preset_ids
    # Special objects are tagged with a real (1-based) area.
    assert all(o.area >= 1 for o in everything.sm64_special_objects)


def test_dialogs_have_text(everything):
    # Dialog text should be non-empty and ids should be unique.
    assert all(d.text for d in everything.sm64_dialogs)
    ids = [d.dialog_id for d in everything.sm64_dialogs]
    assert len(ids) == len(set(ids))


def test_levels_reference_known_courses(everything):
    course_names = {c.course_name for c in everything.sm64_courses}
    level_courses = {lvl.course_name for lvl in everything.sm64_levels}
    # Every course a level points at should be a defined course.
    assert level_courses <= course_names


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
