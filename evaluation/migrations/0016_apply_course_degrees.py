# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def apply_degrees(apps, schema_editor):
    Degree = apps.get_model("evaluation", "Degree")
    Course = apps.get_model("evaluation", "Course")

    ba = Degree.objects.get(name_en='Bachelor')
    ma = Degree.objects.get(name_en='Master')
    ot = Degree.objects.get(name_en='Other')

    for c in Course.objects.all():
        if c.degree == 'Bachelor':
            c.degrees.add(ba)
        elif c.degree == 'Master':
            c.degrees.add(ma)
        else:
            c.degrees.add(ot)
        c.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0015_initial_degrees'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='degrees',
            field=models.ManyToManyField(verbose_name='degrees', to='evaluation.Degree', default=1),
            preserve_default=False,
        ),
        migrations.RunPython(apply_degrees),
    ]
