# Generated by Django 5.1.4 on 2024-12-19 19:31

import django.db.models.deletion
import simple_history.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("census", "0001_initial"),
        ("location", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Church",
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
                    models.CharField(max_length=255, verbose_name="Local Church Name"),
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "census_record",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="church_details",
                        to="census.religiouscensusrecord",
                    ),
                ),
                (
                    "city",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="location.city",
                    ),
                ),
                (
                    "county",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="location.county",
                    ),
                ),
                (
                    "state",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT, to="location.state"
                    ),
                ),
                (
                    "unlisted_location",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to="location.unlistedlocation",
                    ),
                ),
            ],
            options={
                "verbose_name": "Church",
                "verbose_name_plural": "Churches",
            },
        ),
        migrations.CreateModel(
            name="HistoricalChurch",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True, blank=True, db_index=True, verbose_name="ID"
                    ),
                ),
                (
                    "name",
                    models.CharField(max_length=255, verbose_name="Local Church Name"),
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
                        to="census.religiouscensusrecord",
                    ),
                ),
                (
                    "city",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="location.city",
                    ),
                ),
                (
                    "county",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="location.county",
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
                    "state",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="location.state",
                    ),
                ),
                (
                    "unlisted_location",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="location.unlistedlocation",
                    ),
                ),
            ],
            options={
                "verbose_name": "historical Church",
                "verbose_name_plural": "historical Churches",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="HistoricalMembership",
            fields=[
                (
                    "id",
                    models.BigIntegerField(
                        auto_created=True, blank=True, db_index=True, verbose_name="ID"
                    ),
                ),
                ("male_members", models.PositiveIntegerField(default=0)),
                ("female_members", models.PositiveIntegerField(default=0)),
                ("members_under_13", models.PositiveIntegerField(default=0)),
                ("members_13_and_older", models.PositiveIntegerField(default=0)),
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
                        to="census.religiouscensusrecord",
                    ),
                ),
                (
                    "church",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="church.church",
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
                "verbose_name": "historical membership",
                "verbose_name_plural": "historical memberships",
                "ordering": ("-history_date", "-history_id"),
                "get_latest_by": ("history_date", "history_id"),
            },
            bases=(simple_history.models.HistoricalChanges, models.Model),
        ),
        migrations.CreateModel(
            name="Membership",
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
                ("male_members", models.PositiveIntegerField(default=0)),
                ("female_members", models.PositiveIntegerField(default=0)),
                ("members_under_13", models.PositiveIntegerField(default=0)),
                ("members_13_and_older", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "census_record",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membership_details",
                        to="census.religiouscensusrecord",
                    ),
                ),
                (
                    "church",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="membership",
                        to="church.church",
                    ),
                ),
            ],
        ),
    ]