# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0032_populate_rating_answer_counters'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gradeanswercounter',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='gradeanswercounter',
            name='contribution',
        ),
        migrations.RemoveField(
            model_name='gradeanswercounter',
            name='question',
        ),
        migrations.AlterUniqueTogether(
            name='likertanswercounter',
            unique_together=set([]),
        ),
        migrations.RemoveField(
            model_name='likertanswercounter',
            name='contribution',
        ),
        migrations.RemoveField(
            model_name='likertanswercounter',
            name='question',
        ),
        migrations.DeleteModel(
            name='GradeAnswerCounter',
        ),
        migrations.DeleteModel(
            name='LikertAnswerCounter',
        ),
    ]
