# Generated by Django 5.1.5 on 2025-02-18 20:36

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("census", "0013_alter_censusschedule_datascribe_original_image_path_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicalreligiousbody",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="The name of the church as it appears in the census record.",
                max_length=255,
                null=True,
                verbose_name="Local Church Name",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="name",
            field=models.CharField(
                blank=True,
                help_text="The name of the church as it appears in the census record.",
                max_length=255,
                null=True,
                verbose_name="Local Church Name",
            ),
        ),
    ]
