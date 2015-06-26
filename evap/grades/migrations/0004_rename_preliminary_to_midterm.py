# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations


def rename(apps, schema_editor):
    GradeDocument = apps.get_model('grades', 'GradeDocument')
    for grade_document in GradeDocument.objects.all():
        if grade_document.type == 'PRE':
            grade_document.type = 'MID'
            grade_document.save()


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0003_add_upload_path_and_change_last_modified_user_related_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gradedocument',
            name='type',
            field=models.CharField(max_length=3, default='MID', choices=[('MID', 'midterm grades'), ('FIN', 'final grades')], verbose_name='grade type'),
        ),
        migrations.RunPython(rename),
    ]
