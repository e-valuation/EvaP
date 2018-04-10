# -*- coding: utf-8 -*-
from django.db import migrations
from evap import settings


def create_dropout_questionnaire(apps, schema_editor):
    Questionnaire = apps.get_model('evaluation', 'Questionnaire')
    Questionnaire.objects.get_or_create(name_en=settings.DROPOUT_QUESTIONNAIRE_NAME_EN,
                                        name_de=settings.DROPOUT_QUESTIONNAIRE_NAME_DE)


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0063_add_heading_question_type'),
    ]

    operations = [
        migrations.RunPython(create_dropout_questionnaire),
    ]
