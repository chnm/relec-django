# Generated by Django 5.1.4 on 2024-12-19 19:39

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("church", "0001_initial"),
        ("education", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sundayschool",
            name="church",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="sunday_school",
                to="church.church",
            ),
        ),
        migrations.AlterField(
            model_name="vacationbibleschool",
            name="church",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="vb_school",
                to="church.church",
            ),
        ),
    ]
