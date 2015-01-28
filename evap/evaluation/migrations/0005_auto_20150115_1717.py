# -*- coding: utf-8 -*-


from django.db import models, migrations


class Migration(migrations.Migration):

    dependencies = [
        ('evaluation', '0004_evaluation_start_email_template'),
    ]

    operations = [
        migrations.AlterField(
            model_name='questionnaire',
            name='index',
            field=models.IntegerField(default=0, verbose_name='ordering index'),
            preserve_default=True,
        ),
    ]
