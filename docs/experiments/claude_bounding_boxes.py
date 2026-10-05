"""One-off test: can Claude locate answers on 1926 Schedule 1 scans?

Writes results.json and overlays/<model>_<id>.jpg next to this file.
"""

import base64
import glob
import io
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import anthropic
import requests
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
API = "https://religiousecologies.org/census/api/religious-bodies/{}/"
GEMINI = Path("/Users/jheppler/work/chnm/relec-django/gemini/denominations")
MODELS = ["claude-sonnet-5", "claude-opus-5-5"]
LONG_EDGE = 1568

FIELDS = {
    "census_code": "Red-pencil two-part census code handwritten near the top left (e.g. 0-1)",
    "urban_rural_code": "Red-pencil U or R letter in the left margin near lines c-d",
    "date_received": "Date-received rubber stamp near the top right",
    "denomination_code_stamp": "Handwritten three-part denomination code near the top right (e.g. 1-2-3)",
    "b": "b. Division (Association, Conference, Diocese, ...) answer",
    "c": "c. Local name of church answer",
    "d": "d. City, town, village, or township answer",
    "1": "1. Male members", "2": "2. Female members", "3": "3. Total number of members",
    "4": "4. Under 13 years of age", "5": "5. 13 years old and over", "6": "6. Total number of members (by age)",
    "7": "7. Number of church edifices", "8": "8. Value of church edifices", "9": "9. Debt on church edifices",
    "10": "10. Does church own pastor's residence (Yes/No)", "11": "11. Value of pastor's residence",
    "12": "12. Debt on pastor's residence",
    "13": "13. Amount expended for salaries, repairs, ...", "14": "14. Amount expended for benevolences, ...",
    "15": "15. Total expenditures during year",
    "16": "16. Sunday school officers and teachers", "17": "17. Sunday school scholars",
    "18": "18. Summer vacation Bible school officers and teachers", "19": "19. Vacation Bible school scholars",
    "20": "20. Week-day religious school officers and teachers", "21": "21. Week-day school scholars",
    "22": "22. Parochial school administrative officers", "23a": "23a. Elementary teachers",
    "23b": "23b. Secondary teachers", "24a": "24a. Elementary scholars", "24b": "24b. Secondary scholars",
    "25": "25. Name of pastor", "26": "26. Number of ordained assistant pastors",
    "27": "27. Number of other churches served by the pastor",
    "28": "28. Pastor's college", "29": "29. Pastor's theological seminary",
    "30": "30. Assistant pastor's college", "31": "31. Assistant pastor's theological seminary",
    "respondent_name": "Signature of person furnishing information",
    "respondent_title": "Official title (next to the signature)",
    "respondent_date_signed": "Date at the bottom left",
    "respondent_po_address": "P.O. Address at the bottom right",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "boxes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "enum": list(FIELDS)},
                    "x0": {"type": "integer"}, "y0": {"type": "integer"},
                    "x1": {"type": "integer"}, "y1": {"type": "integer"},
                },
                "required": ["key", "x0", "y0", "x1", "y1"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["boxes"],
    "additionalProperties": False,
}


def prompt(width, height):
    fields = "\n".join(f"- {k}: {v}" for k, v in FIELDS.items())
    return (
        f"This is a scan of a 1926 U.S. Census of Religious Bodies Schedule 1 form, "
        f"{width}x{height} pixels. For each field below that has something written, "
        "stamped, or typed in its answer space, give a tight bounding box around that "
        "answer (the handwriting/stamp itself, not the printed question text), in pixel "
        "coordinates of this image: x0,y0 top-left and x1,y1 bottom-right. Omit fields "
        f"whose answer space is blank.\n\nFields:\n{fields}"
    )


def load_image(record_id):
    meta = requests.get(API.format(record_id), timeout=30).json()
    raw = requests.get(meta["urls"]["image"], timeout=60).content
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.thumbnail((LONG_EDGE, LONG_EDGE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return meta["denomination_details"]["name"], img, buf.getvalue()


def locate(client, model, img, jpeg):
    response = client.messages.create(
        model=model,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                         "data": base64.standard_b64encode(jpeg).decode()}},
            {"type": "text", "text": prompt(*img.size)},
        ]}],
    )
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"{model}: stop_reason={response.stop_reason}")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    w, h = img.size
    boxes = {}
    for b in data["boxes"]:
        y0, y1 = sorted((b["y0"], b["y1"]))
        x0, x1 = sorted((b["x0"], b["x1"]))
        boxes[b["key"]] = [round(y0 * 1000 / h), round(x0 * 1000 / w),
                           round(y1 * 1000 / h), round(x1 * 1000 / w)]
    return boxes, response.usage.input_tokens, response.usage.output_tokens


def draw(img, boxes, path):
    out = img.copy()
    d = ImageDraw.Draw(out)
    w, h = out.size
    for key, (y0, x0, y1, x1) in boxes.items():
        rect = [x0 * w / 1000, y0 * h / 1000, x1 * w / 1000, y1 * h / 1000]
        d.rectangle(rect, outline=(225, 29, 72), width=3)
        d.text((rect[0], rect[1] - 11), key, fill=(225, 29, 72))
    out.save(path, quality=80)


def gemini_boxes(record_id):
    import re
    pat = re.compile(r"^q(\d+[ab]?|[a-f])_")
    for f in GEMINI.glob(f"*/records/{record_id}.json"):
        locs = json.loads(f.read_text())["extraction"]["field_locations"] or {}
        out = {}
        for path, box in locs.items():
            if len(box) != 4:
                continue
            leaf = path.rsplit(".", 1)[-1]
            m = pat.match(leaf)
            key = m.group(1) if m else {"denomination_code": "census_code", "urban_rural": "urban_rural_code"}.get(leaf)
            if path.startswith("assistant_pastors"):
                key = {"q30_college": "30", "q31_theological_seminary": "31"}.get(leaf)
            if key:
                out.setdefault(key, box)
        return out
    return None


def main():
    random.seed(1926)
    gemini_ids = [int(Path(p).stem) for p in glob.glob(str(GEMINI / "*/records/*.json"))]
    ids = random.sample(gemini_ids, 8) + [5000, 60000, 120000, 180000] + random.sample(range(1, 227000), 8)
    client = anthropic.Anthropic()
    (HERE / "overlays").mkdir(exist_ok=True)

    def run(record_id):
        try:
            denom, img, jpeg = load_image(record_id)
        except Exception as exc:  # noqa: BLE001 - one-off script, skip bad records
            return {"id": record_id, "error": f"image: {exc}"}
        row = {"id": record_id, "denomination": denom, "size": img.size,
               "gemini": gemini_boxes(record_id), "models": {}}
        for model in MODELS:
            try:
                boxes, tin, tout = locate(client, model, img, jpeg)
            except Exception as exc:  # noqa: BLE001
                row["models"][model] = {"error": str(exc)}
                continue
            row["models"][model] = {"boxes": boxes, "input_tokens": tin, "output_tokens": tout}
            try:
                draw(img, boxes, HERE / "overlays" / f"{model}_{record_id}.jpg")
            except Exception as exc:  # noqa: BLE001
                print("draw failed", record_id, model, exc, file=sys.stderr)
        print(record_id, denom, file=sys.stderr)
        return row

    with ThreadPoolExecutor(6) as pool:
        rows = list(pool.map(run, ids))
    (HERE / "results.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
