from django.apps import AppConfig


class CensusConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "census"

    def ready(self):
        from easy_thumbnails.signal_handlers import generate_aliases_global
        from easy_thumbnails.signals import saved_file

        # Generate every thumbnail alias at upload time so templates never
        # have to generate them during a request (see
        # census/templatetags/census_thumbnails.py). Backfill for existing
        # images: manage.py generate_thumbnails.
        saved_file.connect(generate_aliases_global)
