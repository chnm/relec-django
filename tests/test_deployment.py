import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from config.settings import DEFAULT_CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("module_name", ["config.asgi", "config.wsgi"])
def test_deployment_entry_point_uses_default_settings(module_name):
    env = os.environ.copy()
    env.pop("DJANGO_SETTINGS_MODULE", None)

    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_default_transcription_batch_fits_the_worker_pod_memory():
    manifest = (PROJECT_ROOT / "k8s" / "transcription-worker.yaml").read_text()
    limit_mib = int(re.search(r"limits: \{[^}]*memory: (\d+)Mi", manifest).group(1))

    # Serializing and sending holds the batch about three times over, on top of
    # the Django process itself.
    peak_mib = 3 * DEFAULT_CLAUDE_TRANSCRIPTION_MAX_BATCH_BYTES / 2**20 + 256

    assert peak_mib <= limit_mib
