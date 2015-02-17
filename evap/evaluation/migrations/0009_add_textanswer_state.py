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
            field=models.CharField(choices=[('N', 'not published'), ('P', 'published privately'), ('Y', 'published'), ('', 'not reviewed')], default='', verbose_name='state of answer', max_length=1),
            preserve_default=True,
        ),
    ]
