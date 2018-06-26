from django.db import models, migrations
import django.db.models.deletion
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0029_user_sorting_and_related_names_to_contribution'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GradeDocument',
            fields=[
                ('id', models.AutoField(serialize=False, primary_key=True, verbose_name='ID', auto_created=True)),
                ('file', models.FileField(verbose_name='File', upload_to='')),
                ('type', models.CharField(max_length=3, verbose_name='grade type', choices=[('PRE', 'preliminary grades'), ('FIN', 'final grades')], default='PRE')),
                ('description', models.TextField(verbose_name='Description', max_length=255)),
                ('last_modified_time', models.DateTimeField(verbose_name='Created', auto_now=True)),
                ('course', models.ForeignKey(to='evaluation.Course', related_name='grade_documents', verbose_name='Course', on_delete=django.db.models.deletion.CASCADE)),
                ('last_modified_user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', blank=True, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Grade Document',
                'verbose_name_plural': 'Grade Documents',
            },
        ),
    ]
