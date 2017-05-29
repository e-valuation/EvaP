# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0025_single_result_questionnaire'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gradeanswercounter',
            unique_together=set([('question', 'contribution', 'answer')]),
        ),
        migrations.AlterUniqueTogether(
            name='likertanswercounter',
            unique_together=set([('question', 'contribution', 'answer')]),
        ),
    ]
