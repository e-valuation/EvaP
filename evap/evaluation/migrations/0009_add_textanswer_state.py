from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0008_make_course_state_protected'),
    ]

    operations = [
        migrations.AddField(
            model_name='textanswer',
            name='state',
            field=models.CharField(verbose_name='state of answer', default='NR', max_length=2, choices=[('HI', 'hidden'), ('PU', 'published'), ('PR', 'private'), ('NR', 'not reviewed')]),
        ),
    ]
