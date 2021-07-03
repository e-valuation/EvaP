from django.db import migrations, models


def set_initial_values(apps, _schema_editor):
    TEXT = 0
    HEADING = 5

    Question = apps.get_model('evaluation', 'Question')
    for question in Question.objects.all():
        if question.type not in [TEXT, HEADING]:
            question.allows_additional_textanswers = True
            question.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0120_use_django_db_models_jsonfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='question',
            name='allows_additional_textanswers',
            field=models.BooleanField(default=False, verbose_name='allow additional text answers'),
        ),
        migrations.RunPython(set_initial_values, reverse_code=migrations.RunPython.noop),
        migrations.AlterField(
            model_name='question',
            name='allows_additional_textanswers',
            field=models.BooleanField(default=True, verbose_name='allow additional text answers'),
        ),
    ]
