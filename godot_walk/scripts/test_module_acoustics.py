"""Tests for the library module -> acoustic table (#200)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from deterministic_json import ROOT
from gmap_library import load_library
from gmap_palette_registry import ACOUSTIC_TAGS
from module_acoustics import INDEX, check, mapping_document


def test_committed_module_acoustics_match_accepted_poetics():
    library = load_library(ROOT / INDEX)
    assert check(library) == []
    document = mapping_document(library)
    expected = {f"{module.module_id}@{module.version}" for module in library.modules}
    assert set(document["modules"]) == expected
    for key, record in document["modules"].items():
        assert record["acoustic"] in (*ACOUSTIC_TAGS, "default"), key
        poetics = record["poetics"]
        assert (ROOT / poetics["path"]).is_file(), key
        assert poetics["sha256"]
