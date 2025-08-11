import importlib

from django.db import migrations

original_migration_module = importlib.import_module("evap.evaluation.migrations.0145_rename_degree_to_program")


class Migration(migrations.Migration):
    """
    We forgot to migrate log entries in 0145, so this migration fixes this.
    0145 is now modified to migrate the log entries in the first place.
    """

    dependencies = [
        ("evaluation", "0149_evaluation_dropout_count_alter_questionnaire_type"),
    ]

    operations = [
        migrations.RunPython(original_migration_module.logentries_degrees_to_programs, migrations.RunPython.noop)
    ]
