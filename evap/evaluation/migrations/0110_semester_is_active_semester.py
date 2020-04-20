from django.db import migrations, models


def mark_last_semester_as_active(apps, _schema_editor):
    Semester = apps.get_model("evaluation", "Semester")
    last_semester = Semester.objects.order_by("created_at").last()
    if last_semester is not None:
        last_semester.is_active_semester = True
        last_semester.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0109_questionnaire_is_locked'),
    ]

    operations = [
        migrations.AddField(
            model_name='semester',
            name='is_active_semester',
            field=models.BooleanField(default=None, unique=True, blank=True, null=True, verbose_name='semester is active'),
        ),
        migrations.RunPython(
            mark_last_semester_as_active,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
