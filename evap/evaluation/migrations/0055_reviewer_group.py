# -*- coding: utf-8 -*-

from django.contrib.auth.models import Group
from django.db import models, migrations


def add_group(apps, schema_editor):
    Group.objects.create(name="Reviewer")


def delete_group(apps, schema_editor):
    Group.objects.get(name="Reviewer").delete()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0054_userprofile_language'),
    ]

    operations = [
        migrations.RunPython(add_group, reverse_code=delete_group),
    ]
