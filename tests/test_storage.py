import os
import subprocess
import sys

# Settings are read once at import, so evaluate them in a fresh interpreter.
SCRIPT = """
import django
django.setup()
from django.core.files.storage import default_storage
print(default_storage.url("census_images/originals/a b.jpg"))
"""


def test_object_storage_media_urls_are_unsigned_and_same_origin():
    env = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "config.settings",
        "DJANGO_READ_DOT_ENV_FILE": "False",
        "APP_FQDN": "dev.religiousecologies.org",
        "OBJ_STORAGE": "True",
        "OBJ_STORAGE_ACCESS_KEY_ID": "GKtest",
        "OBJ_STORAGE_SECRET_ACCESS_KEY": "secret",
        "OBJ_STORAGE_BUCKET_NAME": "religiousecologies.org",
        "OBJ_STORAGE_ENDPOINT_URL": "http://obj.rrchnm.internal:3900",
        "OBJ_STORAGE_REGION": "rrchnm",
    }
    url = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert url == (
        "https://dev.religiousecologies.org/media/census_images/originals/a%20b.jpg"
    )
