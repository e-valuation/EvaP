from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0094_remove_unused_evaluation_fields'),
        ('grades', '0014_rename_course_to_evaluation'),
    ]

    operations = [
        migrations.AddField(
            model_name='gradedocument',
            name='course',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='grade_documents', to='evaluation.Course', verbose_name='course'),
        ),
        migrations.AlterField(
            model_name='gradedocument',
            name='evaluation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='grade_documents', to='evaluation.Evaluation', verbose_name='evaluation'),
        ),
        # this is required to prevent database errors about already existing relations and will be changed back in migration 0017
        migrations.AlterModelTable(
            name='gradedocument',
            table='grades_gradedocument_temp',
        ),
    ]
