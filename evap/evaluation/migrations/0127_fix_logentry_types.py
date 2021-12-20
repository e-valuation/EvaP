import importlib
from django.db import migrations

original_migration_module = importlib.import_module("evap.evaluation.migrations.0123_evaluation_state_fsm_int")


class Migration(migrations.Migration):
    """
    Initially, we forgot to migrate logentries in 0123, so this migration cleans this up.
    Note that 0123 is now modified to also take care of the logentries in the first place.
    """

    dependencies = [
        ("evaluation", "0126_add_textanswer_review_email_template"),
    ]

    operations = [
        migrations.RunPython(original_migration_module.logentries_str_to_int, migrations.RunPython.noop),
    ]
