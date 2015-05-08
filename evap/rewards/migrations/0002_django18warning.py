# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rewards', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='semesteractivation',
            name='semester',
            field=models.OneToOneField(to='evaluation.Semester', related_name='rewards_active'),
        ),
    ]
