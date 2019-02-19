from django.db import migrations


def move_grade_documents_to_course(apps, _schema_editor):
    Evaluation = apps.get_model('evaluation', 'Evaluation')
    for evaluation in Evaluation.objects.all():
        evaluation.course.grade_documents.set(evaluation.grade_documents.all())


def move_grade_documents_to_evaluation(apps, _schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    for course in Course.objects.all():
        course.evaluation.grade_documents.set(course.grade_documents.all())


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0015_add_grade_documents_on_course'),
    ]

    operations = [
        migrations.RunPython(
            move_grade_documents_to_course,
            reverse_code=move_grade_documents_to_evaluation
        ),
    ]
