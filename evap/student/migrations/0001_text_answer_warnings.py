from django.contrib.postgres.fields import ArrayField
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='TextAnswerWarning',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('warning_text_de', models.CharField(max_length=1024, verbose_name='Warning text (German)')),
                ('warning_text_en', models.CharField(max_length=1024, verbose_name='Warning text (English)')),
                ('trigger_strings', ArrayField(base_field=models.CharField(max_length=1024), blank=True, default=list,
                    size=None, verbose_name='Trigger strings (case-insensitive)')),
                ('order', models.IntegerField(default=-1, verbose_name='Warning order')),
            ],
            options={
                'ordering': ['order'],
            },
        ),
    ]
