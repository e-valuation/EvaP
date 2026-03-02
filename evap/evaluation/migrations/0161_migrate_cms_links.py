from django.db import migrations


def delete_cms_id_logentries(apps, _schema_editor):
    LogEntry = apps.get_model("evaluation", "LogEntry")
    for course_entry in LogEntry.objects.filter(content_type__app_label="evaluation", content_type__model="course"):
        if "cms_id" in course_entry.data:
            course_entry.data.pop("cms_id")
            course_entry.save()
    for evaluation_entry in LogEntry.objects.filter(
        content_type__app_label="evaluation", content_type__model="evaluation"
    ):
        if "cms_id" in evaluation_entry.data:
            evaluation_entry.data.pop("cms_id")
            evaluation_entry.save()


def move_to_cms_app(apps, _schema_editor):
    Evaluation = apps.get_model("evaluation", "Evaluation")
    EvaluationLink = apps.get_model("cms", "EvaluationLink")
    Course = apps.get_model("evaluation", "Course")
    CourseLink = apps.get_model("cms", "CourseLink")

    for evaluation in Evaluation.objects.exclude(cms_id=None):
        EvaluationLink.objects.create(evaluation=evaluation, cms_id=evaluation.cms_id)

    for course in Course.objects.exclude(cms_id=None):
        CourseLink.objects.create(course=course, cms_id=course.cms_id)


def move_to_evaluation_app(apps, _schema_editor):
    EvaluationLink = apps.get_model("cms", "EvaluationLink")
    CourseLink = apps.get_model("cms", "CourseLink")

    for evaluation_link in EvaluationLink.objects.all():
        evaluation_link.evaluation.cms_id = evaluation_link.cms_id
        evaluation_link.delete()

    for course_link in CourseLink.objects.all():
        course_link.course.cms_id = course_link.cms_id
        course_link.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("evaluation", "0160_evaluation_staff_notes"),
        ("cms", "0002_courselink_evaluationlink"),
    ]

    operations = [
        migrations.RunPython(move_to_cms_app, move_to_evaluation_app),
        migrations.RunPython(delete_cms_id_logentries, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="course",
            name="cms_id",
        ),
        migrations.RemoveField(
            model_name="evaluation",
            name="cms_id",
        ),
    ]
