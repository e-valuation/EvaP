import importlib
from django.db import migrations

original_migration_module = importlib.import_module("evap.evaluation.migrations.0145_rename_degree_to_program")

class Migration(migrations.Migration):
    """
    We forgot to migrate log entries in 0145, so this migrations fixes this.
    0145 is now modified to migrate the log entries in the first place.
    """

    dependencies = [
        ("evaluation", "0148_course_cms_id_evaluation_cms_id"),
    ]

    operations = [
        migrations.RunPython(original_migration_module.logentries_degrees_to_programs, migrations.RunPython.noop)
    ]
