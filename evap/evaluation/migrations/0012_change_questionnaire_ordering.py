from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0011_remove_textanswer_checked_and_hidden'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='questionnaire',
            options={'verbose_name_plural': 'questionnaires', 'verbose_name': 'questionnaire', 'ordering': ('index', 'name_de')},
        ),
    ]
