from django.core.management.commands import shell


class Command(shell.Command):
    def get_auto_imports(self):
        return super().get_auto_imports() + [
            "django.conf.settings",
            "django.contrib.auth.get_user_model",
            "django.core.cache.cache",
            "django.db.models.Avg",
            "django.db.models.Case",
            "django.db.models.Count",
            "django.db.models.Exists",
            "django.db.models.F",
            "django.db.models.Max",
            "django.db.models.Min",
            "django.db.models.OuterRef",
            "django.db.models.Prefetch",
            "django.db.models.Q",
            "django.db.models.Subquery",
            "django.db.models.Sum",
            "django.db.models.When",
            "django.db.transaction",
            "django.urls.resolve",
            "django.urls.reverse",
            "django.urls.reverse",
            "django.utils.timezone",
        ]
