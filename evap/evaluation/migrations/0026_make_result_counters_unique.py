from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0025_single_result_questionnaire'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='gradeanswercounter',
            unique_together={('question', 'contribution', 'answer')},
        ),
        migrations.AlterUniqueTogether(
            name='likertanswercounter',
            unique_together={('question', 'contribution', 'answer')},
        ),
    ]
