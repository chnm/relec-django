from django.db import migrations

# ponytail: queryset.update() skips simple_history, so this conversion leaves
# no per-record history rows; the migration itself is the record.
FORWARD = {"urban": "U", "rural": "R"}
BACKWARD = {"U": "Urban", "R": "Rural"}


def to_letters(apps, schema_editor):
    ReligiousBody = apps.get_model("census", "ReligiousBody")
    for word, letter in FORWARD.items():
        ReligiousBody.objects.filter(urban_rural_code__iexact=word).update(
            urban_rural_code=letter
        )
        ReligiousBody.objects.filter(urban_rural_code=letter.lower()).update(
            urban_rural_code=letter
        )


def to_words(apps, schema_editor):
    ReligiousBody = apps.get_model("census", "ReligiousBody")
    for letter, word in BACKWARD.items():
        ReligiousBody.objects.filter(urban_rural_code=letter).update(
            urban_rural_code=word
        )


class Migration(migrations.Migration):

    dependencies = [
        ("census", "0030_run_publication"),
    ]

    operations = [
        migrations.RunPython(to_letters, to_words),
    ]
