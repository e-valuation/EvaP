from django.db import models, migrations
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0021_django_1_8_upgrade'),
    ]

    operations = [
        migrations.CreateModel(
            name='GradeAnswerCounter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('answer', models.IntegerField(verbose_name='answer')),
                ('count', models.IntegerField(verbose_name='count', default=0)),
                ('contribution', models.ForeignKey(to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE)),
                ('question', models.ForeignKey(to='evaluation.Question', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name_plural': 'grade answers',
                'verbose_name': 'grade answer',
            },
        ),
        migrations.CreateModel(
            name='LikertAnswerCounter',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, verbose_name='ID', serialize=False)),
                ('answer', models.IntegerField(verbose_name='answer')),
                ('count', models.IntegerField(verbose_name='count', default=0)),
                ('contribution', models.ForeignKey(to='evaluation.Contribution', on_delete=django.db.models.deletion.CASCADE)),
                ('question', models.ForeignKey(to='evaluation.Question', on_delete=django.db.models.deletion.CASCADE)),
            ],
            options={
                'verbose_name_plural': 'Likert answers',
                'verbose_name': 'Likert answer',
            },
        ),
    ]
