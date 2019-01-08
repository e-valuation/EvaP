from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0089_use_integers_for_question_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='question',
            name='type',
            field=models.PositiveSmallIntegerField(
                choices=(
                    ('Text', (
                        (0, 'Text question'),
                    )),
                    ('Unipolar Likert', (
                        (1, 'Agreement question'),
                    )),
                    ('Grade', (
                        (2, 'Grade question'),
                    )),
                    ('Bipolar Likert', (
                        (6, 'Easy-difficult question'),
                        (7, 'Few-many question'),
                        (8, 'Little-much question'),
                        (9, 'Small-large question'),
                        (10, 'Slow-fast question'),
                    )),
                    ('Yes-no', (
                        (3, 'Positive yes-no question'),
                        (4, 'Negative yes-no question'),
                    )),
                    ('Layout', (
                        (5, 'Heading'),
                    ))
                ),
                verbose_name='question type'
            ),
        ),
    ]
