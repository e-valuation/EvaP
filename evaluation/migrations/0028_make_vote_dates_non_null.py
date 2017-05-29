# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0027_course_is_required_for_reward'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='vote_end_date',
            field=models.DateField(verbose_name='last day of evaluation'),
        ),
        migrations.AlterField(
            model_name='course',
            name='vote_start_date',
            field=models.DateField(verbose_name='first day of evaluation'),
        ),
    ]
