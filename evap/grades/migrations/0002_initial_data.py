# -*- coding: utf-8 -*-

from django.db import models, migrations
from django.contrib.auth.models import Group


def add_group(apps, schema_editor):
    Group.objects.create(name="Grade publisher")


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(add_group),
    ]
