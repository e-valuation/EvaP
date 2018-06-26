from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0010_fill_textanswer_state'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='textanswer',
            name='checked',
        ),
        migrations.RemoveField(
            model_name='textanswer',
            name='hidden',
        ),
    ]
