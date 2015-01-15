# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0004_evaluation_start_email_template'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questionnaire',
            name='index',
            field=models.IntegerField(default=0, verbose_name='ordering index', blank=True),
            preserve_default=True,
        ),
    ]
