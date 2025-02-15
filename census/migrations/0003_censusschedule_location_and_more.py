# Generated by Django 5.1.5 on 2025-01-22 21:23

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("census", "0002_historicalcensusschedule_and_more"),
        ("location", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="censusschedule",
            name="location",
            field=models.ForeignKey(
                default=None,
                on_delete=django.db.models.deletion.PROTECT,
                to="location.location",
            ),
        ),
        migrations.AddField(
            model_name="historicalcensusschedule",
            name="location",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="location.location",
            ),
        ),
    ]
