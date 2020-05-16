from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


def fill_import_names(apps, _schema_editor):
    Degree = apps.get_model('evaluation', 'Degree')
    for degree in Degree.objects.all():
        degree.import_names = [degree.name_de]
        degree.save()

    CourseType = apps.get_model('evaluation', 'CourseType')
    for course_type in CourseType.objects.all():
        course_type.import_names = [course_type.name_de]
        course_type.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0112_evaluation_allow_editors_to_edit'),
    ]

    operations = [
        migrations.AddField(
            model_name='degree',
            name='import_names',
            field=ArrayField(
                base_field=models.CharField(max_length=1024),
                default=list,
                size=None,
                verbose_name='import names',
                blank=True,
            ),
        ),
        migrations.AddField(
            model_name='coursetype',
            name='import_names',
            field=ArrayField(
                base_field=models.CharField(max_length=1024),
                default=list,
                size=None,
                verbose_name='import names',
                blank=True,
            ),
        ),
        migrations.RunPython(
            fill_import_names,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
