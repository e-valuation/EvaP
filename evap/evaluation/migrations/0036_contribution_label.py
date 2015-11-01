# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0035_contribution_comment_visibility'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribution',
            name='label',
            field=models.CharField(blank=True, max_length=255, verbose_name='label', null=True),
        ),
    ]
