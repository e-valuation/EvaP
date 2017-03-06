# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0006_archiving_and_order_default'),
    ]

    operations = [
        migrations.AlterField(
            model_name='course',
            name='state',
            field=django_fsm.FSMField(max_length=50, default='new'),
            preserve_default=True,
        ),
    ]
