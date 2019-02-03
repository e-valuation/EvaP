from django.db import migrations


def make_single_result_questionnaire_general(apps, _schema_editor):
    Questionnaire = apps.get_model('evaluation', 'Questionnaire')
    Evaluation = apps.get_model('evaluation', 'Evaluation')
    Contribution = apps.get_model('evaluation', 'Contribution')

    questionnaire = Questionnaire.objects.get(name_en='Single result')
    questionnaire.is_for_contributors = False
    questionnaire.save()

    for evaluation in Evaluation.objects.filter(is_single_result=True):
        contribution = Contribution.objects.get(evaluation=evaluation)
        contribution.contributor = None
        contribution.can_edit = False
        contribution.textanswer_visibility = 'OWN'
        contribution.save()


def make_single_result_questionnaire_for_contributors(apps, _schema_editor):
    Questionnaire = apps.get_model('evaluation', 'Questionnaire')
    Evaluation = apps.get_model('evaluation', 'Evaluation')
    Course = apps.get_model('evaluation', 'Course')
    Contribution = apps.get_model('evaluation', 'Contribution')

    questionnaire = Questionnaire.objects.get(name_en='Single result')
    questionnaire.is_for_contributors = True
    questionnaire.save()

    for evaluation in Evaluation.objects.filter(is_single_result=True):
        course = Course.objects.get(pk=evaluation.course.pk)
        contribution = Contribution.objects.get(evaluation=evaluation)
        contribution.contributor = course.responsibles.first()
        contribution.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0097_remove_contribution_responsible'),
    ]

    operations = [
        migrations.RunPython(
            make_single_result_questionnaire_general,
            reverse_code=make_single_result_questionnaire_for_contributors
        ),
    ]
