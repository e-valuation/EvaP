from django.db import models, migrations


def apply_degrees(apps, _schema_editor):
    Degree = apps.get_model("evaluation", "Degree")
    Course = apps.get_model("evaluation", "Course")

    bachelor = Degree.objects.get(name_en='Bachelor')
    master = Degree.objects.get(name_en='Master')
    other = Degree.objects.get(name_en='Other')

    for course in Course.objects.all():
        if course.degree == 'Bachelor':
            course.degrees.add(bachelor)
        elif course.degree == 'Master':
            course.degrees.add(master)
        else:
            course.degrees.add(other)
        course.save()


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0015_initial_degrees'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='degrees',
            field=models.ManyToManyField(verbose_name='degrees', to='evaluation.Degree', default=1),
            preserve_default=False,
        ),
        migrations.RunPython(apply_degrees),
    ]
