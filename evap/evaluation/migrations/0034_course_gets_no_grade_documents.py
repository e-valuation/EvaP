from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0033_remove_likert_and_grade_answer'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='gets_no_grade_documents',
            field=models.BooleanField(default=False, verbose_name='gets no grade documents'),
        ),
    ]
