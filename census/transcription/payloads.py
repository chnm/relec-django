"""Build frozen, image-bearing Claude requests for schedule jobs."""

import base64
import json
import mimetypes

from django.conf import settings


class PayloadError(ValueError):
    pass


SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


def read_schedule_image(schedule):
    if not schedule.original_image:
        raise PayloadError("Schedule has no original image.")
    media_type = mimetypes.guess_type(schedule.original_image.name)[0] or "image/jpeg"
    if media_type not in SUPPORTED_IMAGE_TYPES:
        raise PayloadError(f"Unsupported image type: {media_type}.")
    try:
        with schedule.original_image.open("rb") as image_file:
            image_bytes = image_file.read(
                settings.CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES + 1
            )
    except Exception as exc:
        raise PayloadError(
            "The original image could not be read from storage."
        ) from exc
    if len(image_bytes) > settings.CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES:
        raise PayloadError("Schedule image exceeds the configured byte limit.")
    encoded = base64.b64encode(image_bytes)
    if len(encoded) > settings.CLAUDE_TRANSCRIPTION_MAX_IMAGE_BYTES:
        raise PayloadError("Base64 schedule image exceeds the configured byte limit.")
    return media_type, encoded.decode("ascii")


def schedule_context(schedule):
    county = schedule.county
    places = []
    if county:
        places = list(
            county.places.exclude(place_id=None)
            .order_by("name", "place_id")
            .values("place_id", "name")
        )
    return {
        "schedule": {
            "resource_id": schedule.resource_id,
            "schedule_id": schedule.schedule_id,
            "title": schedule.schedule_title,
            "denomination": (
                schedule.schedule_denomination.name
                if schedule.schedule_denomination_id
                else None
            ),
            "known_county": county.name if county else None,
            "known_state": county.state.code if county else None,
        },
        "populated_place_candidates": places,
    }


def build_batch_request(job):
    metadata = job.run.metadata
    media_type, image_data = read_schedule_image(job.census_schedule)
    context = json.dumps(schedule_context(job.census_schedule), sort_keys=True)
    params = {
        "model": metadata["model"],
        "max_tokens": metadata["max_tokens"],
        "system": metadata["prompt"],
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Transcribe this schedule. Context:\n" + context,
                    },
                ],
            }
        ],
        "output_config": {
            "format": {
                "type": "json_schema",
                "schema": metadata["transport_schema"],
            }
        },
    }
    # Historical runs intentionally omit these keys and retain the request
    # behavior frozen when they were launched. New model-specific controls are
    # provenance.
    if "thinking" in metadata:
        params["thinking"] = metadata["thinking"]
    if "output_effort" in metadata:
        params["output_config"]["effort"] = metadata["output_effort"]
    return {"custom_id": job.custom_id, "params": params}
