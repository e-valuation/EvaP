# -*- coding: utf-8 -*-


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
        ('evaluation', '0003_auto_add_course_is_graded'),
    ]

    operations = [
        migrations.RunPython(insert_emailtemplates),
    ]
