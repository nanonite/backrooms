"""Put the pipeline modules and this directory on ``sys.path`` for the tests.

The pipeline's modules import each other by bare name (``from video_probe import
VideoMetadata``), because they are executed as scripts from their own directory.
That is right for the CLI and wrong for a test runner, so the path is set up
here once rather than repeated in every test module.

It also makes ``build_colmap_model`` -- the writer that produces COLMAP-format
models for the registration tests -- importable by name.
"""

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
PIPELINE_DIR = TESTS_DIR.parent

for _path in (PIPELINE_DIR, TESTS_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
