# Manual migration to drop old Page tables and create new BlogPost/Visualization tables

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0001_initial"),
    ]

    operations = [
        # Drop the old tables if they exist
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS pages_historicalpage CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.RunSQL(
            sql="DROP TABLE IF EXISTS pages_page CASCADE;",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
