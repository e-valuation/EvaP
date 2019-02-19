from django.db import migrations


def move_data_to_course(apps, _schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    Evaluation = apps.get_model('evaluation', 'Evaluation')
    for evaluation in Evaluation.objects.all():
        course = Course.objects.create(
            name_de=evaluation.name_de,
            name_en=evaluation.name_en,
            is_graded=evaluation.is_graded,
            is_private=evaluation.is_private,
            gets_no_grade_documents=evaluation.gets_no_grade_documents,
            semester=evaluation.semester,
            type=evaluation.type,
        )
        course.degrees.set(evaluation.degrees.all())
        evaluation.course = course
        evaluation.save()


def move_data_to_evaluation(apps, _schema_editor):
    Course = apps.get_model('evaluation', 'Course')
    Evaluation = apps.get_model('evaluation', 'Evaluation')
    for course in Course.objects.all():
        evaluation = Evaluation.objects.get(course=course)
        evaluation.name_de = course.name_de
        evaluation.name_en = course.name_en
        evaluation.is_graded = course.is_graded
        evaluation.is_private = course.is_private
        evaluation.gets_no_grade_documents = course.gets_no_grade_documents
        evaluation.semester = course.semester
        evaluation.type = course.type
        evaluation.save()

        evaluation.degrees.set(course.degrees.all())


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0092_add_course'),
    ]

    operations = [
        migrations.RunPython(
            move_data_to_course,
            reverse_code=move_data_to_evaluation
        ),
    ]
