# Generated by Django 5.1.7 on 2025-05-15 20:53

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Location",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("place_id", models.IntegerField()),
                ("state", models.CharField(max_length=2)),
                ("city", models.CharField(max_length=250)),
                ("county", models.CharField(max_length=50)),
                ("map_name", models.CharField(max_length=50)),
                ("county_ahcb", models.CharField(max_length=50)),
                ("lat", models.FloatField()),
                ("lon", models.FloatField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="HistoricalLocation",
            fields=[
                ("id", models.IntegerField(blank=True, db_index=True)),
                ("place_id", models.IntegerField()),
                ("state", models.CharField(max_length=2)),
                ("city", models.CharField(max_length=250)),
                ("county", models.CharField(max_length=50)),
                ("map_name", models.CharField(max_length=50)),
                ("county_ahcb", models.CharField(max_length=50)),
                ("lat", models.FloatField()),
                ("lon", models.FloatField()),
                ("created_at", models.DateTimeField(blank=True, editable=False)),
                ("updated_at", models.DateTimeField(blank=True, editable=False)),
                ("history_id", models.AutoField(primary_key=True, serialize=False)),
                ("history_date", models.DateTimeField(db_index=True)),
                ("history_change_reason", models.CharField(max_length=100, null=True)),
                (
                    "history_type",
                    models.CharField(
                        choices=[("+", "Created"), ("~", "Changed"), ("-", "Deleted")],
                        max_length=1,
                    ),
                ),
                (
                    "history_user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "historical location",
                "verbose_name_plural": "historical locations",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
    ]
