from django.apps import AppConfig


class ReligiousEcologiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "religious_ecologies"

    def ready(self):
        import religious_ecologies.admin  # noqa
