# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0023_create_answer_counters'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='gradeanswer',
            name='contribution',
        ),
        migrations.RemoveField(
            model_name='gradeanswer',
            name='question',
        ),
        migrations.RemoveField(
            model_name='likertanswer',
            name='contribution',
        ),
        migrations.RemoveField(
            model_name='likertanswer',
            name='question',
        ),
        migrations.DeleteModel(
            name='GradeAnswer',
        ),
        migrations.DeleteModel(
            name='LikertAnswer',
        ),
    ]
