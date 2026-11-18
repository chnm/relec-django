"""Move the allowed models and pricing out of settings into TranscriptionModel.

Reads the CLAUDE_TRANSCRIPTION_MODELS / CLAUDE_TRANSCRIPTION_PRICING env vars
those settings used, so a deployment that overrode them keeps its values; falls
back to the old defaults. Models without pricing are skipped, since a launch
with them was already refused.
"""

import json
import os

from django.db import migrations

DEFAULT_MODELS = ["claude-sonnet-4-6", "claude-sonnet-5"]
DEFAULT_PRICING = {
    "effective_date": "2026-08-11",
    "source": "https://platform.claude.com/docs/en/about-claude/pricing",
    "models": {
        "claude-sonnet-4-6": {
            "rates": {
                "input_tokens": "1.50",
                "output_tokens": "7.50",
                "cache_creation_input_tokens": "1.875",
                "cache_creation_1h_input_tokens": "3.00",
                "cache_read_input_tokens": "0.15",
            }
        },
        "claude-sonnet-5": {
            "rates": {
                "input_tokens": "1.00",
                "output_tokens": "5.00",
                "cache_creation_input_tokens": "1.25",
                "cache_creation_1h_input_tokens": "2.00",
                "cache_read_input_tokens": "0.10",
            }
        },
    },
}
# Was hard-coded in census.transcription.services.inference_config_for_model.
INFERENCE_CONFIG = {
    "claude-sonnet-5": {"thinking": {"type": "adaptive"}, "output_effort": "low"},
}


def seed(apps, schema_editor):
    TranscriptionModel = apps.get_model("census", "TranscriptionModel")
    env_models = os.environ.get("CLAUDE_TRANSCRIPTION_MODELS", "").strip()
    model_ids = (
        [m.strip() for m in env_models.split(",") if m.strip()]
        if env_models
        else DEFAULT_MODELS
    )
    env_pricing = os.environ.get("CLAUDE_TRANSCRIPTION_PRICING", "").strip()
    catalog = json.loads(env_pricing) if env_pricing else DEFAULT_PRICING

    for order, model_id in enumerate(model_ids):
        config = catalog.get("models", {}).get(model_id)
        if not config or not config.get("rates"):
            continue
        rates = config["rates"]
        TranscriptionModel.objects.get_or_create(
            model_id=model_id,
            defaults={
                "sort_order": order,
                "input_rate": rates["input_tokens"],
                "output_rate": rates["output_tokens"],
                "cache_creation_rate": rates["cache_creation_input_tokens"],
                "cache_creation_1h_rate": rates["cache_creation_1h_input_tokens"],
                "cache_read_rate": rates["cache_read_input_tokens"],
                "pricing_effective_date": config.get(
                    "effective_date", catalog["effective_date"]
                ),
                "pricing_valid_through": config.get("valid_through"),
                "pricing_source": config.get("source", catalog["source"]),
                "inference_config": INFERENCE_CONFIG.get(model_id, {}),
            },
        )


class Migration(migrations.Migration):
    dependencies = [("census", "0032_transcription_model")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
