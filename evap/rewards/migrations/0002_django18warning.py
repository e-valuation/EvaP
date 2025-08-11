import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("rewards", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="semesteractivation",
            name="semester",
            field=models.OneToOneField(
                to="evaluation.Semester", related_name="rewards_active", on_delete=django.db.models.deletion.CASCADE
            ),
        ),
    ]
