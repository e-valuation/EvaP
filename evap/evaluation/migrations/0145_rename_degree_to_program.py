from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0144_alter_evaluation_state"),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Degree',
            new_name='Program',
        ),
        migrations.RenameField(
            model_name='course',
            old_name='degrees',
            new_name='programs',
        ),
        migrations.AlterField(
            model_name="course",
            name="programs",
            field=models.ManyToManyField(related_name="courses", to="evaluation.program", verbose_name="programs"),
        ),
        migrations.AlterField(
            model_name="program",
            name="order",
            field=models.IntegerField(default=-1, verbose_name="program order"),
        ),
    ]
