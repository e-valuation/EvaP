from django.db import migrations


def add_single_result_questionnaire(apps, _schema_editor):
    Questionnaire = apps.get_model('evaluation', 'Questionnaire')
    Question = apps.get_model('evaluation', 'Question')

    questionnaire = Questionnaire(name_de='Einzelergebnis', name_en='Single result', is_for_contributors=True, obsolete=True)
    questionnaire.save()
    question = Question(questionnaire=questionnaire, text_de='Einzelergebnis', text_en='Single result', type='G')
    question.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0024_remove_likertanswers_and_gradeanswers'),
    ]

    operations = [
        migrations.RunPython(add_single_result_questionnaire),
    ]
