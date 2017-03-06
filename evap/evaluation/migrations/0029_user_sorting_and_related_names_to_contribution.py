# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0028_make_vote_dates_non_null'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='userprofile',
            options={'verbose_name_plural': 'users', 'ordering': ('last_name', 'first_name', 'username'), 'verbose_name': 'user'},
        ),
        migrations.AlterField(
            model_name='gradeanswercounter',
            name='contribution',
            field=models.ForeignKey(related_name='gradeanswercounter_set', to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AlterField(
            model_name='likertanswercounter',
            name='contribution',
            field=models.ForeignKey(related_name='likertanswercounter_set', to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE),
        ),
        migrations.AlterField(
            model_name='textanswer',
            name='contribution',
            field=models.ForeignKey(related_name='textanswer_set', to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE),
        ),
    ]
