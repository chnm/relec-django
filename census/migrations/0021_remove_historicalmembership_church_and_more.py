# Generated by Django 5.1.5 on 2025-03-24 21:24

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("census", "0020_alter_censusschedule_box_alter_censusschedule_notes_and_more"),
        ("location", "0008_alter_historicallocation_county_ahcb_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="historicalmembership",
            name="church",
        ),
        migrations.RemoveField(
            model_name="membership",
            name="church",
        ),
        migrations.RemoveField(
            model_name="historicalchurch",
            name="census_record",
        ),
        migrations.RemoveField(
            model_name="historicalchurch",
            name="history_user",
        ),
        migrations.RemoveField(
            model_name="historicalchurch",
            name="location",
        ),
        migrations.CreateModel(
            name="HistoricalReligiousBody",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True, blank=True, db_index=True, verbose_name="ID"
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=255, verbose_name="Local religious body name"
                    ),
                ),
                ("census_code", models.CharField(max_length=50)),
                ("division", models.CharField(max_length=100)),
                ("address", models.CharField(blank=True, max_length=255, null=True)),
                ("urban_rural_code", models.CharField(max_length=50)),
                (
                    "num_edifices",
                    models.PositiveIntegerField(blank=True, default=0, null=True),
                ),
                (
                    "edifice_value",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                (
                    "edifice_debt",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                ("has_pastors_residence", models.BooleanField(default=False)),
                (
                    "residence_value",
                    models.DecimalField(decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "residence_debt",
                    models.DecimalField(decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "expenses",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "benevolences",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "total_expenditures",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
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
                    "census_record",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="census.censusschedule",
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
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="location.location",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Religious Body",
                "verbose_name_plural": "historical Religious Bodies",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="ReligiousBody",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        max_length=255, verbose_name="Local religious body name"
                    ),
                ),
                ("census_code", models.CharField(max_length=50)),
                ("division", models.CharField(max_length=100)),
                ("address", models.CharField(blank=True, max_length=255, null=True)),
                ("urban_rural_code", models.CharField(max_length=50)),
                (
                    "num_edifices",
                    models.PositiveIntegerField(blank=True, default=0, null=True),
                ),
                (
                    "edifice_value",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                (
                    "edifice_debt",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True
                    ),
                ),
                ("has_pastors_residence", models.BooleanField(default=False)),
                (
                    "residence_value",
                    models.DecimalField(decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "residence_debt",
                    models.DecimalField(decimal_places=2, max_digits=12, null=True),
                ),
                (
                    "expenses",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "benevolences",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                (
                    "total_expenditures",
                    models.DecimalField(decimal_places=2, default=0, max_digits=12),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "census_record",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="church_details",
                        to="census.censusschedule",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="location.location",
                    ),
                ),
            ],
            options={
                "verbose_name": "Religious Body",
                "verbose_name_plural": "Religious Bodies",
            },
        ),
        migrations.AddField(
            model_name="historicalmembership",
            name="religious_body",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="+",
                to="census.religiousbody",
            ),
        ),
        migrations.AddField(
            model_name="membership",
            name="religious_body",
            field=models.OneToOneField(
                default=None,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="membership",
                to="census.religiousbody",
            ),
        ),
        migrations.DeleteModel(
            name="Church",
        ),
        migrations.DeleteModel(
            name="HistoricalChurch",
        ),
    ]
