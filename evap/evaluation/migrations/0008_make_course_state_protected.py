# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0007_fsmfield_python3'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='state',
            field=django_fsm.FSMField(default='new', protected=True, max_length=50),
            preserve_default=True,
        ),
    ]
