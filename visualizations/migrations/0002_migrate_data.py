"""
Data migration: copy pages.Visualization and datalayers.DataLayerSource
into the new visualizations.Visualization model.
"""
from datetime import datetime, timezone

from django.db import migrations


def forward(apps, schema_editor):
    OldVisualization = apps.get_model("pages", "Visualization")
    DataLayerSource = apps.get_model("datalayers", "DataLayerSource")
    NewVisualization = apps.get_model("visualizations", "Visualization")

    # Determine which old slugs have custom views (hardcoded in URLs)
    CUSTOM_VIEW_SLUGS = {
        "denomination-map": "denomination_map",
        "demographics-map": "demographics_map",
        "populated-places-map": "denomination_geojson_map",
        "urban-congregations": "urban_congregations_map",
        "cities-map": "urban_congregations_map",
    }

    # 1. Copy pages.Visualization records
    for old in OldVisualization.objects.all():
        render_type = "custom" if old.slug in CUSTOM_VIEW_SLUGS else "model"
        custom_view_name = CUSTOM_VIEW_SLUGS.get(old.slug, "")

        NewVisualization.objects.create(
            title=old.title,
            slug=old.slug,
            author=old.author,
            published_date=old.published_date,
            updated_date=old.updated_date,
            content=old.content,
            abstract=old.abstract,
            thumbnail_image=old.thumbnail_image.name if old.thumbnail_image else "",
            thumbnail_description=old.thumbnail_description,
            doi=old.doi,
            script_file=old.script_file or "",
            style_file=old.style_file or "",
            render_type=render_type,
            custom_view_name=custom_view_name,
        )

    # 2. Copy datalayers.DataLayerSource records (skip if slug already exists)
    for source in DataLayerSource.objects.all():
        if NewVisualization.objects.filter(slug=source.slug).exists():
            continue

        # Convert DateField to DateTimeField
        pub_date = source.published_date
        if pub_date:
            pub_date = datetime.combine(pub_date, datetime.min.time(), tzinfo=timezone.utc)

        NewVisualization.objects.create(
            title=source.title,
            slug=source.slug,
            author=source.author,
            published_date=pub_date,
            content=source.content,
            abstract=source.abstract,
            thumbnail_image=source.thumbnail_image.name if source.thumbnail_image else "",
            doi=source.doi,
            render_type="datalayer",
            datalayer_source=source.slug,
        )


def backward(apps, schema_editor):
    NewVisualization = apps.get_model("visualizations", "Visualization")
    NewVisualization.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("visualizations", "0001_initial"),
        ("pages", "0001_initial"),
        ("datalayers", "0004_datalayersource_content_and_more"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
