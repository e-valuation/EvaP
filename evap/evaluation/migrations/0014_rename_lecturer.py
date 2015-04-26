# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def rename_lecturer(apps, schema_editor):
    Course = apps.get_model("evaluation", "Course")
    Course.objects.filter(state="lecturerApproved").update(state="editorApproved")

    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.filter(name="Lecturer Review Notice").update(name="Editor Review Notice")

def rename_lecturer_reverse(apps, schema_editor):
    Course = apps.get_model("evaluation", "Course")
    Course.objects.filter(state="editorApproved").update(state="lecturerApproved")

    EmailTemplate = apps.get_model("evaluation", "EmailTemplate")
    EmailTemplate.objects.filter(name="Editor Review Notice").update(name="Lecturer Review Notice")


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0013_rename_kind_to_type'),
    ]

    operations = [
        migrations.RunPython(rename_lecturer, reverse_code=rename_lecturer_reverse),
    ]
