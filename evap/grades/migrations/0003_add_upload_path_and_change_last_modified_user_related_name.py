import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import evap.grades.models


class Migration(migrations.Migration):

    dependencies = [
        ("grades", "0002_initial_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gradedocument",
            name="file",
            field=models.FileField(verbose_name="File", upload_to=evap.grades.models.helper_upload_path),
        ),
        migrations.AlterField(
            model_name="gradedocument",
            name="last_modified_user",
            field=models.ForeignKey(
                blank=True,
                related_name="last_modified_user+",
                to=settings.AUTH_USER_MODEL,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
            ),
        ),
    ]
