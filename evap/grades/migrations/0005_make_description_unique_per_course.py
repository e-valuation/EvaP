# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0004_rename_preliminary_to_midterm'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gradedocument',
            unique_together=set([('course', 'description')]),
        ),
    ]
