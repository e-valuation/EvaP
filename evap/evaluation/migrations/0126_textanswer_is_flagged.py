# Generated by Django 3.0.10 on 2020-10-26 18:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0125_use_lists_for_ordering'),
    ]

    operations = [
        migrations.AddField(
            model_name='textanswer',
            name='is_flagged',
            field=models.BooleanField(default=False, verbose_name='reviewer flag'),
        ),
    ]