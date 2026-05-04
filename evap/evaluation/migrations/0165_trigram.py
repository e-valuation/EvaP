from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("evaluation", "0164_remove_questionnaire_questionnaire_visibility_choices_and_more"),
    ]

    operations = [TrigramExtension()]
