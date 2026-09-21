"""Seed the public AI statement page.

The page is an ordinary `pages.Page` row so editors can revise it in the admin
after deployment. The migration only creates it when no page with the slug
exists; it never overwrites edits made through the admin.
"""

from django.db import migrations

SLUG = "ai-statement"

TITLE = "Our Use of AI"

META_DESCRIPTION = (
    "How American Religious Ecologies uses AI to transcribe 1926 census schedules, "
    "and how every transcription is reviewed and recorded."
)

CONTENT = """\
_American Religious Ecologies_ is digitizing the 1926 U.S. Census of Religious Bodies, which contains individual schedules for approximately 232,000 congregations. For several years student research assistants transcribed these schedules by hand. Their work established the project's data standards, and it remains the baseline against which everything else is measured. But at that pace the full census would have taken decades. Beginning in 2026 we started using a large language model to produce first-draft transcriptions, and this page explains how that works, what the model does and does not decide, and how we keep the record of who transcribed what.

## What the model does

Each schedule is a single handwritten or typed form describing one congregation: its name, location, denomination, membership, finances, buildings, Sunday schools, and pastor. We send an image of the form to Anthropic's Claude model together with a written set of transcription instructions and a fixed data schema. The model reads the image and returns a structured record with every field it can read, along with notes on anything it found illegible or ambiguous. The instructions tell the model that it is always correct to flag a field rather than guess.

The model is a transcriber, nothing more. It does not interpret the census, write text for this site, or generate data that is not on the form. When it cannot match a denomination or place name to our reference lists, it leaves that field empty for a person to resolve rather than inventing an answer.

## Every transcription is reviewed by a person

A model transcription enters the project in exactly the same state as a student transcription did: **Needs Review**. Nothing the model produces becomes part of the published dataset until a member of the project team has reviewed it.

Reviewers work in a comparison view that shows the original schedule image beside the model's transcription and, where one exists, the earlier human transcription. They accept or correct each value field by field, and they must confirm their decision before it is applied. Before we began using the model, we froze a snapshot of every existing human transcription so that it can always be compared against and restored. Records that a reviewer has already approved are never overwritten by a model run.

For large runs, we first evaluate the model on a sample of schedules that has been transcribed by hand, covering clear and difficult handwriting, blank and zero-heavy forms, and a range of regions and denominations. We compare the model's output against that sample field by field, and we track the cost and speed of each run separately from its accuracy. A cheaper or faster run is not accepted if it makes more errors or takes reviewers longer to correct.

## We keep the record

Because this is historical data, we treat the transcription process itself as part of the scholarly record. For every model run we permanently store the model version, the exact instructions and schema it was given, and cryptographic hashes of both, so the run can be reproduced or audited later. The model's raw output is stored unchanged and cannot be edited or deleted. When a reviewer accepts, corrects, or reverses a value, that decision is recorded alongside the sources it drew on. Each record's history shows whether a value came from a student transcriber, from the model, or from a reviewer's correction, and any reviewed change can be reversed without losing the evidence behind it.

## Why we do this

Our goal is a complete, congregation-level dataset of American religion in 1926 that researchers can trust and cite. Machine transcription lets us reach the whole census within the life of the project. Human review, frozen baselines, and full provenance are how we make sure that speed does not come at the expense of accuracy or accountability.

If you have questions about our methods or find an error in the data, please [contact us](mailto:chnm@gmu.edu). We welcome corrections.
"""


def create_page(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    Page.objects.get_or_create(
        slug=SLUG,
        defaults={
            "title": TITLE,
            "content": CONTENT,
            "meta_description": META_DESCRIPTION,
            "is_published": True,
            "show_in_nav": True,
            "nav_title": "AI Statement",
            "nav_order": 3,
        },
    )


def delete_page(apps, schema_editor):
    Page = apps.get_model("pages", "Page")
    Page.objects.filter(slug=SLUG).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0008_remove_historicalvisualization_history_user_and_more"),
    ]

    operations = [
        migrations.RunPython(create_page, delete_page),
    ]
