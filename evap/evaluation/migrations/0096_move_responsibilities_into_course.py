from django.db import migrations


def move_data_to_course(apps, _schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    Contribution = apps.get_model('evaluation', 'Contribution')
    for course in Course.objects.all():
        responsibles = [contribution.contributor for contribution in Contribution.objects.filter(evaluation=course.evaluation, responsible=True)]
        course.responsibles.set(responsibles)


def move_data_to_contribution(apps, _schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    Contribution = apps.get_model('evaluation', 'Contribution')
    for course in Course.objects.all():
        for contribution in Contribution.objects.filter(evaluation=course.evaluation, contributor__in=course.responsibles.all()):
            contribution.responsible = True
            contribution.can_edit = True
            contribution.textanswer_visibility = 'GENERAL'
            contribution.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0095_add_course_responsibles'),
    ]

    operations = [
        migrations.RunPython(
            move_data_to_course,
            reverse_code=move_data_to_contribution
        ),
    ]
