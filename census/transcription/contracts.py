"""Versioned prompt/schema loading and candidate validation."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator

CONTRACT_VERSION = "relec-1926-v1"
BASE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = BASE_DIR / "prompts" / f"{CONTRACT_VERSION}.md"
SCHEMA_PATH = BASE_DIR / "schemas" / f"{CONTRACT_VERSION}.json"


class CandidateValidationError(ValueError):
    pass


def _read_bytes(path):
    return path.read_bytes()


def load_contract():
    prompt_bytes = _read_bytes(PROMPT_PATH)
    schema_bytes = _read_bytes(SCHEMA_PATH)
    schema = json.loads(schema_bytes)
    Draft202012Validator.check_schema(schema)
    transport_schema = build_transport_schema(schema)
    transport_bytes = json.dumps(
        transport_schema, sort_keys=True, separators=(",", ":")
    ).encode()
    return {
        "version": CONTRACT_VERSION,
        "prompt": prompt_bytes.decode("utf-8"),
        "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
        "schema": schema,
        "schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
        "transport_schema": transport_schema,
        "transport_schema_sha256": hashlib.sha256(transport_bytes).hexdigest(),
    }


def build_transport_schema(candidate_schema):
    """Adapt the candidate contract to Anthropic's supported schema subset."""
    schema = deepcopy(candidate_schema)
    schema.pop("$schema", None)
    schema.pop("$id", None)

    def append_description(node, text):
        description = node.get("description", "").strip()
        node["description"] = f"{description} {text}".strip()

    def convert(node):
        if isinstance(node, list):
            for item in node:
                convert(item)
            return
        if not isinstance(node, dict):
            return

        if "minimum" in node:
            minimum = node.pop("minimum")
            append_description(node, f"Non-null values must be at least {minimum}.")
        if "minItems" in node:
            minimum_items = node.pop("minItems")
            append_description(
                node,
                f"Must contain at least {minimum_items} item(s).",
            )

        node_type = node.get("type")
        if isinstance(node_type, list) and "null" in node_type:
            concrete = next(item for item in node_type if item != "null")
            if concrete == "boolean":
                node["type"] = "integer"
                node["enum"] = [-1, 0, 1]
                append_description(
                    node,
                    "Transport: -1=null, 0=false, 1=true.",
                )
            else:
                node["type"] = concrete
                if concrete == "integer":
                    append_description(node, "Transport: -1 means null.")
                elif concrete == "string":
                    append_description(
                        node,
                        "Transport: an empty string means null.",
                    )
            if "enum" in node:
                node["enum"] = ["" if item is None else item for item in node["enum"]]

        for value in node.values():
            convert(value)

    convert(schema)
    return schema


def normalize_transport_candidate(candidate):
    """Convert provider transport sentinels back into the candidate contract."""
    schema = load_contract()["schema"]

    def resolve(node):
        reference = node.get("$ref") if isinstance(node, dict) else None
        if not reference:
            return node
        target = schema
        for part in reference.removeprefix("#/").split("/"):
            target = target[part]
        return target

    def normalize(value, node):
        node = resolve(node)
        node_type = node.get("type")
        nullable = isinstance(node_type, list) and "null" in node_type
        concrete = (
            next(item for item in node_type if item != "null")
            if nullable
            else node_type
        )
        if nullable:
            if concrete == "string" and value == "":
                return None
            if concrete == "integer" and value == -1:
                return None
            if concrete == "boolean":
                if value == -1:
                    return None
                if value in (0, 1):
                    return bool(value)
        if concrete == "object" and isinstance(value, dict):
            properties = node.get("properties", {})
            return {
                key: normalize(item, properties.get(key, {}))
                for key, item in value.items()
            }
        if concrete == "array" and isinstance(value, list):
            return [normalize(item, node.get("items", {})) for item in value]
        return value

    return normalize(candidate, schema)


def validate_candidate(candidate, schedule):
    """Validate the frozen contract and schedule-local place constraint."""
    contract = load_contract()
    errors = sorted(
        Draft202012Validator(contract["schema"]).iter_errors(candidate),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        error = errors[0]
        path = ".".join(str(part) for part in error.absolute_path) or "$"
        raise CandidateValidationError(f"{path}: {error.message}")

    place_id = candidate["schedule_fields"]["populated_place_id"]
    if place_id is not None:
        if schedule.county_id is None:
            raise CandidateValidationError(
                "populated_place_id cannot be selected without a schedule county"
            )
        if not schedule.county.places.filter(place_id=place_id).exists():
            raise CandidateValidationError(
                "populated_place_id is not one of this schedule county's candidates"
            )
    return candidate
