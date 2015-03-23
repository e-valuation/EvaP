# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0010_fill_textanswer_state'),
    ]

    operations = [
    	migrations.RemoveField(
            model_name='textanswer',
            name='checked',
        ),
        migrations.RemoveField(
            model_name='textanswer',
            name='hidden',
        ),
    ]
