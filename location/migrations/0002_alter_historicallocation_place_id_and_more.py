# Generated by Django 5.1.7 on 2025-05-15 21:01

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("location", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="historicallocation",
            name="place_id",
            field=models.IntegerField(null=True),
        ),
        migrations.AlterField(
            model_name="location",
            name="place_id",
            field=models.IntegerField(null=True),
        ),
    ]
