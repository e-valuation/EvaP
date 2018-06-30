from django.db import models, migrations


def set_comment_visibility(apps, _schema_editor):
    Contribution = apps.get_model('evaluation', 'Contribution')
    for c in Contribution.objects.all():
        if c.responsible:
            c.comment_visibility = "ALL"
            c.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0034_course_gets_no_grade_documents'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribution',
            name='comment_visibility',
            field=models.CharField(default='OWN', max_length=10, verbose_name='comment visibility', choices=[('OWN', 'Own'), ('COURSE', 'Course'), ('ALL', 'All')]),
        ),
        migrations.RunPython(set_comment_visibility),
    ]
