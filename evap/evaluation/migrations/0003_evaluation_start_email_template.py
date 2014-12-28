# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def insert_emailtemplates(apps, schema_editor):
    emailtemplates = [
        ("Evaluation Started", "[EvaP] A course is available for evaluation"),
    ]

    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")

    for name, subject in emailtemplates:
        if not EmailTemplate.objects.filter(name=name).exists():
           EmailTemplate.objects.create(name=name, subject=subject, body="")


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0002_initial_data'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplates),
    ]
