from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0012_change_questionnaire_ordering'),
    ]

    operations = [
        migrations.RenameField(
            model_name='course',
            old_name='kind',
            new_name='type',
        ),
        migrations.RenameField(
            model_name='question',
            old_name='kind',
            new_name='type',
        ),
        migrations.AlterField(
            model_name='question',
            name='type',
            field=models.CharField(verbose_name='question type', choices=[('T', 'Text Question'), ('L', 'Likert Question'), ('G', 'Grade Question')], max_length=1),
            preserve_default=True,
        ),
    ]
