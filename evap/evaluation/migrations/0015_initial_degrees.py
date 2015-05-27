# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def create_degrees(apps, schema_editor):
    degrees = [
        ("Bachelor", "Bachelor"),
        ("Master", "Master"),
        ("Sonstige", "Other"),
    ]

    Degree = apps.get_model("evaluation", "Degree")

    for name_de, name_en in degrees:
        if not Degree.objects.filter(name_de=name_de).exists():
           Degree.objects.create(name_de=name_de, name_en=name_en)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0014_create_degree_model'),
    ]

    operations = [
        migrations.RunPython(create_degrees),
    ]
