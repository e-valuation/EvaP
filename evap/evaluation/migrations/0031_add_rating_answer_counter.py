# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0030_change_course_ordering'),
    ]

    operations = [
        migrations.CreateModel(
            name='RatingAnswerCounter',
            fields=[
                ('id', models.AutoField(auto_created=True, verbose_name='ID', serialize=False, primary_key=True)),
                ('answer', models.IntegerField(verbose_name='answer')),
                ('count', models.IntegerField(verbose_name='count', default=0)),
                ('contribution', models.ForeignKey(related_name='ratinganswercounter_set', to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE)),
                ('question', models.ForeignKey(to='evaluation.Question', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name': 'rating answer',
                'verbose_name_plural': 'rating answers',
            },
        ),
        migrations.AlterUniqueTogether(
            name='ratinganswercounter',
            unique_together=set([('question', 'contribution', 'answer')]),
        ),
    ]
