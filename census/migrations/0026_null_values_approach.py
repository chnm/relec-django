from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("census", "0025_clergy_serving_congregation_and_more"),
    ]

    operations = [
        # ReligiousBody
        migrations.AlterField(
            model_name="religiousbody",
            name="num_edifices",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Number of edifices",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="edifice_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Value of church edifices",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="edifice_debt",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Debt on church edifices",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="has_pastors_residence",
            field=models.BooleanField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Ownership of pastor's residence",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="residence_value",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Value of pastor's residence",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="residence_debt",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Debt on pastor's residence",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="expenses",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Expenses",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="benevolences",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Benevolences",
            ),
        ),
        migrations.AlterField(
            model_name="religiousbody",
            name="total_expenditures",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Leave blank if information is missing or illegible",
                max_digits=12,
                null=True,
                verbose_name="Total annual expenditures",
            ),
        ),
        # Membership
        migrations.AlterField(
            model_name="membership",
            name="male_members",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Male Members",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="female_members",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Female Members",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="total_members_by_sex",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Total Members by Sex",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="members_under_13",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Members Under 13",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="members_13_and_older",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Members 13 and Older",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="total_members_by_age",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Total Members by Age",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="sunday_school_num_officers_teachers",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Sunday Schools - Number of Officers/Teachers",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="sunday_school_num_scholars",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Sunday Schools - Number of Scholars",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="vbs_num_officers_teachers",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Vacation Bible Schools - Number of Officers/Teachers",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="vbs_num_scholars",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Vacation Bible Schools - Number of Scholars",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="weekday_num_officers_teachers",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Week-day Religious Schools - Number of Officers/Teachers",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="weekday_num_scholars",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Week-day Religious Schools - Number of Scholars",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="parochial_num_administrators",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Parochial Schools - Number of Administrators",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="parochial_num_elementary_teachers",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Parochial Schools - Number of Elementary Teachers",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="parochial_num_secondary_teachers",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Parochial Schools - Number of Secondary Teachers",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="parochial_num_elementary_scholars",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Parochial Schools - Number of Elementary Scholars",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="parochial_num_secondary_scholars",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Parochial Schools - Number of Secondary Scholars",
            ),
        ),
        # Clergy
        migrations.AlterField(
            model_name="clergy",
            name="name",
            field=models.CharField(
                help_text="The name of the clergy person. Leave blank if information is missing or illegible.",
                max_length=255,
            ),
        ),
        migrations.AlterField(
            model_name="clergy",
            name="college",
            field=models.CharField(
                blank=True,
                help_text="The college attended by the clergy person. Leave blank if information is missing or illegible.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="clergy",
            name="theological_seminary",
            field=models.CharField(
                blank=True,
                help_text="The theological seminary attended by the clergy person. Leave blank if information is missing or illegible.",
                max_length=255,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="clergy",
            name="num_other_churches_served",
            field=models.IntegerField(
                blank=True,
                help_text="Leave blank if information is missing or illegible",
                null=True,
                verbose_name="Number of other churches served",
            ),
        ),
        migrations.AlterField(
            model_name="clergy",
            name="serving_congregation",
            field=models.BooleanField(
                blank=True,
                help_text="Whether the pastor is serving the congregation. Leave blank if information is missing or illegible.",
                null=True,
                verbose_name="Pastor serving congregation",
            ),
        ),
    ]
