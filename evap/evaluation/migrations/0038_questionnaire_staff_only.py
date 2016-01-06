# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0037_specify_on_delete'),
    ]

    operations = [
        migrations.AddField(
            model_name='questionnaire',
            name='staff_only',
            field=models.BooleanField(verbose_name='display for staff only', default=False),
        ),
    ]
