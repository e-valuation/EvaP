# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0008_make_course_state_protected'),
    ]

    operations = [
        migrations.AddField(
            model_name='textanswer',
            name='state',
            field=models.CharField(verbose_name='state of answer', default='not_reviewed', max_length=20, choices=[('hidden', 'hidden'), ('published', 'published'), ('private', 'private'), ('not_reviewed', 'not reviewed')]),
        ),
    ]
