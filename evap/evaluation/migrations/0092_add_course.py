from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0091_rename_course_to_evaluation'),
    ]

    operations = [
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name_de', models.CharField(max_length=1024, verbose_name='name (german)')),
                ('name_en', models.CharField(max_length=1024, verbose_name='name (english)')),
                ('is_graded', models.BooleanField(default=True, verbose_name='is graded')),
                ('is_private', models.BooleanField(default=False, verbose_name='is private')),
                ('gets_no_grade_documents', models.BooleanField(default=False, verbose_name='gets no grade documents')),
                ('last_modified_time', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Last modified')),
                ('degrees', models.ManyToManyField(related_name='courses', to='evaluation.Degree', verbose_name='degrees')),
                ('last_modified_user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='courses_last_modified+', to=settings.AUTH_USER_MODEL)),
                ('semester', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='courses', to='evaluation.Semester', verbose_name='semester')),
                ('type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='courses', to='evaluation.CourseType', verbose_name='course type')),
            ],
            options={
                'verbose_name': 'course',
                'verbose_name_plural': 'courses',
                'ordering': ('name_de',),
                # this is required to prevent database errors about already existing relations and will be changed back in migration 0094
                'db_table': 'evaluation_course_temp',
            },
        ),
        migrations.AddField(
            model_name='evaluation',
            name='course',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='evaluation', to='evaluation.Course', verbose_name='course'),
        ),
        migrations.AlterUniqueTogether(
            name='course',
            unique_together={('semester', 'name_de'), ('semester', 'name_en')},
        ),
        migrations.AlterUniqueTogether(
            name='evaluation',
            unique_together={('course', 'name_de'), ('course', 'name_en')},
        ),
        migrations.AlterField(
            model_name='evaluation',
            name='type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='type', to='evaluation.CourseType', verbose_name='courses'),
        ),
        migrations.AlterField(
            model_name='evaluation',
            name='semester',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='semester', to='evaluation.Semester', verbose_name='courses'),
        ),
    ]
