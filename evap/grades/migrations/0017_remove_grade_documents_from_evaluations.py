from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('grades', '0016_move_grade_documents_to_course'),
    ]

    operations = [
        migrations.AlterField(
            model_name='gradedocument',
            name='course',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='grade_documents', to='evaluation.Course', verbose_name='course'),
        ),
        migrations.AlterUniqueTogether(
            name='gradedocument',
            unique_together={('course', 'description_en'), ('course', 'description_de')},
        ),
        migrations.RemoveField(
            model_name='gradedocument',
            name='evaluation',
        ),
        migrations.AlterModelTable(
            name='gradedocument',
            table=None,
        ),
    ]
