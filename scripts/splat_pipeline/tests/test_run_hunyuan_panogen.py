import sys
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from run_hunyuan_panogen import (
    candidate_specs,
    configure_offload,
    read_env_token,
    validate_panorama_dimensions,
)


def test_reads_only_whitelisted_token_without_evaluating_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OTHER=value\nHF_TOKEN='hf_test-token'\n", encoding="utf-8")
    assert read_env_token(env_file) == "hf_test-token"


def test_ignores_empty_or_invalid_token_values(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "HF_TOKEN=\nHUGGINGFACE_HUB_TOKEN=not a token\n", encoding="utf-8"
    )
    assert read_env_token(env_file) is None


def test_candidate_set_compares_default_and_measured_fov_at_same_seed():
    candidates = candidate_specs([42, 43, 44], 75.93466)
    assert [(item["seed"], item["fov"]) for item in candidates] == [
        (42, 80.0),
        (42, 75.93466),
        (43, 75.93466),
        (44, 75.93466),
    ]


def test_single_seed_makes_default_and_measured_fov_pair():
    candidates = candidate_specs([42], 75.93466)
    assert [(item["seed"], item["fov"]) for item in candidates] == [
        (42, 80.0),
        (42, 75.93466),
    ]


def test_measured_fov_only_skips_upstream_comparison_candidate():
    candidates = candidate_specs([42], 75.93466, include_upstream_fov=False)
    assert [(item["seed"], item["fov"]) for item in candidates] == [(42, 75.93466)]


def test_accepts_reduced_resolution_equirectangular_panorama():
    validate_panorama_dimensions(1536, 768)


def test_rejects_invalid_panorama_dimensions():
    for dimensions in ((1920, 1080), (1536, 760), (0, 0)):
        with pytest.raises(ValueError):
            validate_panorama_dimensions(*dimensions)


def test_sequential_offload_is_applied_after_pipeline_construction():
    class Pipeline:
        sequential_offload_enabled = False

        def enable_sequential_cpu_offload(self):
            self.sequential_offload_enabled = True

    pipeline = Pipeline()
    configure_offload(pipeline, "sequential")
    assert pipeline.sequential_offload_enabled


def test_model_offload_keeps_upstream_configuration():
    class Pipeline:
        sequential_offload_enabled = False

        def enable_sequential_cpu_offload(self):
            self.sequential_offload_enabled = True

    pipeline = Pipeline()
    configure_offload(pipeline, "model")
    assert not pipeline.sequential_offload_enabled
