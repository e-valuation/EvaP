from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0093_move_data_from_evaluation_to_course'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='evaluation',
            name='degrees',
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='gets_no_grade_documents',
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='is_graded',
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='is_private',
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='semester',
        ),
        migrations.RemoveField(
            model_name='evaluation',
            name='type',
        ),
        migrations.AlterField(
            model_name='evaluation',
            name='course',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='evaluation', to='evaluation.Course', verbose_name='course'),
        ),
        migrations.AlterModelTable(
            name='course',
            table=None,
        ),
    ]
